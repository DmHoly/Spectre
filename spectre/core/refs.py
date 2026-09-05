"""Refs: a named, reusable starting point for future experiences - not a new storage concept,
just Follow's own tag (:meth:`follow.storage.repository.Repository.tag`, an immutable pointer to
one experiment) given a short, memorable name and a Spectre-shaped API around it. Every Follow tag
in a Spectre project *is* a ref by construction - Spectre never exposes ad hoc tagging for
anything else, so the two ideas are simply the same thing, the same way :mod:`spectre.core.
versioning` layers a Spectre-specific X.Y.Z on top of Follow's plain commit chain without Follow
needing to know anything structural changed.

A ref is meant to be repeated: many experiences fork off the same one over time (see
``spectre.api.experiments.evolve_experience`` - it already accepts a tag name anywhere it accepts
an id or a branch, since :meth:`follow.storage.repository.Repository.get` resolves all three the
same way), so refs become the graph's stable, memorable landmarks rather than one more version
among many. :func:`ref_graph` collapses everything *between* two refs down to a single edge, the
same way :func:`spectre.core.atlas.condensed_edges` collapses the commits between two branch tips
- so navigating "from ref to ref" only ever surfaces those landmarks; the versions in between are
still on the fiche's own timeline (see :mod:`spectre.core.versioning`), just not here.
"""

from __future__ import annotations

from typing import Any

import follow

from . import versioning
from .atlas import condensed_edges

REF_NAME_PREFIX = "ref v"


class RefNameTakenError(Exception):
    """``name`` is already used by a different experiment - either as another ref, or (tags and
    branches share one namespace in Follow) as a branch name - so it cannot be reused for this
    one. Tags are meant to be a stable, citable reference; silently repointing one defeats the
    point."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


def _version_for(repo: "follow.Repository", experiment_id: str) -> str:
    history = list(reversed(repo.log(experiment_id)))
    return versioning.compute_branch_versions(history)[experiment_id]["version"]


def default_ref_name(repo: "follow.Repository", experiment_id: str) -> str:
    """"ref vX.Y.Z", using the version :mod:`spectre.core.versioning` already computes for this
    experiment - the same number the fiche's own timeline shows next to it, so a ref's default
    name is recognizable at a glance rather than an arbitrary label."""
    return f"{REF_NAME_PREFIX}{_version_for(repo, experiment_id)}"


def _unique_default_name(repo: "follow.Repository", base: str, target_id: str) -> str:
    """``base`` as-is if it's free, or already points at ``target_id`` (calling :func:`create_ref`
    twice on the same experiment with no nickname is idempotent, not an error). Otherwise - two
    different lineages landing on the same X.Y.Z, which can happen since versions reset per
    lineage - disambiguate with a short id suffix rather than handing :meth:`follow.storage.
    repository.Repository.tag` a name it will just as surely reject.
    """
    if base not in repo.tags and base not in repo.branches:
        return base
    if repo.tags.get(base) == target_id:
        return base
    return f"{base}-{target_id[:6]}"


def create_ref(repo: "follow.Repository", ref: str, *, name: str | None = None) -> dict[str, str]:
    """Tag ``ref`` (an id, branch, or existing tag) as a ref: ``name`` if given (a nickname -
    "omega", "banane"...), otherwise :func:`default_ref_name`. Raises
    :class:`follow.ExperimentNotFoundError` if ``ref`` doesn't resolve to anything, or
    :class:`RefNameTakenError` if an explicitly chosen ``name`` is already a different tag or a
    branch.
    """
    experiment = repo.get(ref)
    nickname = name.strip() if name else ""
    final_name = nickname or _unique_default_name(repo, default_ref_name(repo, experiment.id), experiment.id)
    try:
        repo.tag(final_name, at=experiment.id)
    except follow.FollowError as exc:
        raise RefNameTakenError(final_name) from exc
    return {"name": final_name, "experiment_id": experiment.id}


def ref_names_for(repo: "follow.Repository", experiment_id: str) -> list[str]:
    """Every ref name currently pointing at ``experiment_id``, if any - several nicknames can
    point at the same experiment (a Follow tag is just an entry in a name -> id dict), so this is
    a list rather than a single optional name."""
    return sorted(name for name, target in repo.tags.items() if target == experiment_id)


def list_refs(repo: "follow.Repository") -> list[dict[str, Any]]:
    """Every ref in this project, newest first: one entry per distinct tagged experiment (several
    nicknames on the same one collapse into a single entry, its ``names`` carrying all of them),
    each with the version :mod:`spectre.core.versioning` already computes for it.
    """
    by_experiment: dict[str, list[str]] = {}
    for name, experiment_id in repo.tags.items():
        by_experiment.setdefault(experiment_id, []).append(name)

    entries = []
    for experiment_id, names in by_experiment.items():
        experiment = repo.get(experiment_id)
        entries.append(
            {
                "experiment_id": experiment_id,
                "names": sorted(names),
                "title": experiment.title,
                "branch": experiment.branch,
                "status": experiment.conclusion.status,
                "version": _version_for(repo, experiment_id),
                "created_at": experiment.created_at.isoformat(),
            }
        )
    entries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return entries


def ref_graph(repo: "follow.Repository") -> dict[str, Any]:
    """Refs as central nodes, condensed the same way :func:`spectre.core.atlas.condensed_edges`
    collapses branch tips: one ``(ancestor_ref_id, ref_id)`` edge per path from a ref back to its
    nearest ref ancestor, whatever ordinary (non-ref) versions sit in between - so a caller can
    navigate "from ref to ref" without drawing the whole lineage.
    """
    entries = list_refs(repo)
    ref_experiments = [repo.get(entry["experiment_id"]) for entry in entries]
    edges = condensed_edges(repo, ref_experiments)
    return {"nodes": entries, "edges": [{"from": a, "to": b} for a, b in edges]}
