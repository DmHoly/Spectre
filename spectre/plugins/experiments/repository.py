"""Where a microproject's experiments live: its Follow repository (``<microproject dir>/follow``),
read through a cache and written under a lock, and the reading of an experiment that every view
shares - Spectre's own statuses (« hold », « continued ») on top of Follow's four, and the current
tip of each line of study.

- :func:`get_repository` (reading) serves one ``follow.Repository`` per microproject, reloaded
  only when the repository changed on disk (:func:`_signature`) or was written through
  :func:`writing`. The instance is shared between requests: a reader never writes to it.
- :func:`writing` (every write) takes the microproject's lock, reloads the repository *inside* it
  - so a write always starts from the latest tips, never from a copy read before another write -
  and invalidates the cache when it is done. The instance it yields is its own, never the cached
  one.
- :func:`delete_line`, :func:`rename_tag` and :func:`remove_tag` are the only places that reach
  into Follow's private state: Follow has no delete (experiments are immutable, content-addressed)
  and no way to rename or drop a tag (meant to be a stable, citable reference).
- :class:`_Store` is Follow's own JSON layout, written through :func:`spectre.kernel.fs.write_text`:
  under Windows a reader holding ``refs.json`` for an instant no longer fails a commit.
"""

from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from follow.storage.backends import JsonFileStore

from ...kernel import fs, plugin_states
from ...kernel.errors import Conflict
from ...kernel.locks import keyed_lock
from ..microprojects.service import microproject_dir

LOCK_NAMESPACE = "experiments"
# L'id d'une version Follow (``follow.core.ids.content_id``) : ni une piste ni une ref ne peuvent en
# porter la forme (Follow résout un nom avant un id : un tel nom masquerait la version).
VERSION_ID_RE = re.compile(r"^exp_[0-9a-f]{16}$")


def follow_repo_path(slug: str) -> Path:
    return microproject_dir(slug) / "follow"


class _Store(JsonFileStore):
    """``JsonFileStore`` (the layout on disk is unchanged) whose atomic writes go through
    :func:`spectre.kernel.fs.write_text` - retried on a transient ``PermissionError``, like every
    atomic write of Spectre."""

    def add_experiment(self, experiment) -> None:
        fs.write_text(self.path / "objects" / f"{experiment.id}.json", experiment.model_dump_json(indent=2))

    def write_refs(self, branches: dict[str, str], tags: dict[str, str]) -> None:
        fs.write_text(self.path / "refs.json", json.dumps({"branches": branches, "tags": tags}, indent=2, sort_keys=True))


def _load(slug: str):
    import follow

    return follow.Repository(store=_Store(follow_repo_path(slug)))


def _signature(path: Path) -> tuple | None:
    """What changes on disk with every commit: ``refs.json`` is rewritten and a file lands in
    ``objects/`` (the same signature as the plates index, :mod:`spectre.plugins.wafers.service`) -
    ``None`` for a repository nothing was ever committed to."""
    try:
        refs = (path / "refs.json").stat()
    except FileNotFoundError:
        return None
    objects = path / "objects"
    return (refs.st_mtime_ns, refs.st_size, objects.stat().st_mtime_ns if objects.exists() else 0)


# path -> (generation, signature, repository) ; a write bumps the generation of its path, so a
# repository loaded before (or during) that write is never served afterwards, even when the two
# writes fall within the same tick of the file system's clock.
_CACHE: dict[str, tuple[int, tuple, object]] = {}
_GENERATIONS: dict[str, int] = {}
_CACHE_GUARD = threading.Lock()


def get_repository(slug: str):
    """The microproject's ``follow.Repository`` for reading - from the cache when nothing changed
    since it was loaded. Shared between requests: never write to it (see :func:`writing`)."""
    path = follow_repo_path(slug)
    key = str(path)
    with _CACHE_GUARD:
        generation = _GENERATIONS.get(key, 0)
        cached = _CACHE.get(key)
    signature = _signature(path)
    if signature is None:
        return _load(slug)
    if cached and cached[0] == generation and cached[1] == signature:
        return cached[2]
    repo = _load(slug)
    with _CACHE_GUARD:
        if _GENERATIONS.get(key, 0) == generation:
            _CACHE[key] = (generation, signature, repo)
    return repo


@contextmanager
def writing(slug: str) -> Iterator:
    """``with writing(slug) as repo:`` - the microproject's repository, freshly reloaded under its
    lock (one writer at a time per microproject), the cache invalidated on the way out. With the
    intent_forms plugin turned off, the microproject's intent form is not enforced: its questions
    can't be shown, so they can't be answered."""
    key = str(follow_repo_path(slug))
    with keyed_lock(LOCK_NAMESPACE, slug):
        try:
            repo = _load(slug)
            if not plugin_states.is_enabled("intent_forms"):
                repo.commit_form = None
            yield repo
        finally:
            with _CACHE_GUARD:
                _GENERATIONS[key] = _GENERATIONS.get(key, 0) + 1
                _CACHE.pop(key, None)


def delete_line(repo, experiment_id: str) -> list[str]:
    """Delete the line of study ``experiment_id`` (a branch): its tip and its earlier versions,
    back to the point where it forks off another line (a version another branch still needs - its
    tip, or a version derived from it). Refs pointing at a deleted version go with it. Returns the
    deleted version ids - :class:`Conflict` when another line derives from one of this line's own
    versions: the line would only be cut short, not deleted.

    Follow has no delete of its own, so this rewrites its in-memory tables and its JSON store
    directly - the only function of Spectre that touches Follow's private attributes.
    """
    tip_id = repo.branches[experiment_id]
    to_delete: list[str] = []
    current: str | None = tip_id
    while current is not None:
        derived_elsewhere = [e.id for e in repo if current in e.parents and e.id not in to_delete]
        other_tips = [b for b, tip in repo.branches.items() if tip == current and b != experiment_id]
        if derived_elsewhere or other_tips:
            break
        to_delete.append(current)
        parents = repo.get(current).parents
        current = parents[0] if parents else None
    if not to_delete or (current is not None and repo.get(current).branch == experiment_id):
        raise Conflict("D'autres pistes découlent de cette étude - supprimez-les d'abord.", code="has_descendants")

    deleted = set(to_delete)
    for version_id in to_delete:
        repo._objects.pop(version_id, None)
    for name in [n for n, target in repo._tags.items() if target in deleted]:
        repo._tags.pop(name)
    repo._branches.pop(experiment_id, None)
    repo._store.write_refs(dict(repo._branches), dict(repo._tags))
    store_path = getattr(repo._store, "path", None)
    if store_path is not None:
        for version_id in to_delete:
            (store_path / "objects" / f"{version_id}.json").unlink(missing_ok=True)
    return to_delete


def rename_tag(repo, old: str, new: str) -> None:
    """Rename the tag ``old`` to ``new`` (same target), in one write of ``refs.json`` (under
    :func:`writing`). The caller checks that ``new`` is free - tags and branches share one
    namespace in Follow."""
    repo._tags[new] = repo._tags.pop(old)
    repo._store.write_refs(dict(repo._branches), dict(repo._tags))


def remove_tag(repo, name: str) -> None:
    """Drop the tag ``name`` (under :func:`writing`) ; the version it pointed at stays."""
    repo._tags.pop(name)
    repo._store.write_refs(dict(repo._branches), dict(repo._tags))


RETIRED_LINES_FILE = "retired_lines.json"


def retired_lines(slug: str) -> set[str]:
    """The names of the lines deleted from the microproject: never given to a new line, since a
    link to a study names its line (an entity link stays after its line is deleted, see
    :func:`retire_line`) - a reused name would hand it over to an unrelated study."""
    path = follow_repo_path(slug) / RETIRED_LINES_FILE
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("lines", []))
    except FileNotFoundError:
        return set()


def retire_line(slug: str, experiment_id: str) -> None:
    """Record the deleted line ``experiment_id`` (under :func:`writing`): its name is retired for
    good. The links to it (plugin links, which experiments doesn't know) stay listed and
    deletable; the atlas no longer draws them."""
    names = retired_lines(slug) | {experiment_id}
    fs.write_text(follow_repo_path(slug) / RETIRED_LINES_FILE, json.dumps({"lines": sorted(names)}, indent=2))


RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}

# Deux statuts propres à Spectre, en plus des quatre de Follow (draft, running, concluded, abandoned) :
# - « hold » (en pause) : posé à la main (PUT .../status). L'étude garde son statut Follow (brouillon ou
#   en cours - elle compte toujours comme non terminée) et porte metadata["hold"] = {since, by, reason} ;
#   la reprendre, la conclure ou en faire évoluer la structure retire la clé.
# - « continued » (continuée) : déduit, jamais enregistré - un brouillon jamais conclu dont une version
#   suivante a repris le travail (un enfant structurel dans le graphe de filiation).
HOLD_KEY = "hold"


def hold_of(experiment) -> dict | None:
    """The pause on an experiment still in progress (``{"since", "by", "reason"}``), if any."""
    hold = experiment.metadata.get(HOLD_KEY)
    return hold if hold and experiment.conclusion.status in RUNNING_STATUSES else None


def display_status(experiment, *, continued: bool = False) -> str:
    """The status Spectre shows for ``experiment``: Follow's own, « hold » while paused, or
    « continued » for a draft a newer version took up (``continued`` - the caller knows the graph)."""
    if continued and experiment.conclusion.status == "draft":
        return "continued"
    if hold_of(experiment):
        return "hold"
    return experiment.conclusion.status


def branch_tips(repo) -> list:
    """One experiment per line of study (a branch) - its current tip - rather than every version
    ever committed to it: a tag, a piece of evidence or a conclusion each record a new version of
    the same study. The version-by-version history is still there on the fiche itself and on the
    microproject's graph - this only thins out summary lists.
    """
    seen_ids: set[str] = set()
    tips = []
    for tip_id in repo.branches.values():
        if tip_id in seen_ids:
            continue
        seen_ids.add(tip_id)
        tips.append(repo.get(tip_id))
    return tips
