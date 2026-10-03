"""Refs: a named, reusable starting point for future experiences - not a new storage concept,
just Follow's own tag (:meth:`follow.storage.repository.Repository.tag`, an immutable pointer to
one experiment) given a short, memorable name and a Spectre-shaped API around it. Every Follow tag
in a Spectre microproject *is* a ref by construction - Spectre never exposes ad hoc tagging for
anything else, so the two ideas are simply the same thing, the same way
:mod:`spectre.plugins.experiments.versioning` layers a Spectre-specific X.Y.Z on top of Follow's
plain commit chain without Follow needing to know anything structural changed.

A ref is meant to be repeated: many lines of study start from the same one over time (``POST
.../experiments`` with ``from_version``), so refs become the graph's stable, memorable landmarks
rather than one more version among many. :func:`ref_graph` collapses everything *between* two refs down to a single edge, the
same way :func:`spectre.plugins.experiments.lineage.condensed_edges` collapses the commits between two branch tips
- so navigating "from ref to ref" only ever surfaces those landmarks; the versions in between are
still on the fiche's own timeline (see :mod:`spectre.plugins.experiments.versioning`), just not here.
"""

from __future__ import annotations

from typing import Any

import follow

from ...kernel.errors import Conflict, InvalidInput
from . import versioning
from .lineage import condensed_edges
from .repository import display_status

REF_NAME_PREFIX = "ref v"


def _version_for(repo: "follow.Repository", version_id: str) -> str:
    history = list(reversed(repo.log(version_id)))
    return versioning.compute_branch_versions(history)[version_id]["version"]


def default_ref_name(repo: "follow.Repository", version_id: str) -> str:
    """"ref vX.Y.Z", using the version :mod:`spectre.plugins.experiments.versioning` already computes
    for this version - the same number the fiche's own frise shows next to it, so a ref's default
    name is recognizable at a glance rather than an arbitrary label."""
    return f"{REF_NAME_PREFIX}{_version_for(repo, version_id)}"


def _unique_default_name(repo: "follow.Repository", base: str, target_id: str) -> str:
    """``base`` as-is if it's free, or already points at ``target_id`` (calling :func:`create_ref`
    twice on the same version with no nickname is idempotent, not an error). Otherwise - two
    different lineages landing on the same X.Y.Z, which can happen since versions reset per
    lineage - disambiguate with a short id suffix rather than handing
    :meth:`follow.storage.repository.Repository.tag` a name it will just as surely reject.
    """
    if base not in repo.tags and base not in repo.branches:
        return base
    if repo.tags.get(base) == target_id:
        return base
    return f"{base}-{target_id[:6]}"


def create_ref(repo: "follow.Repository", version_id: str, *, name: str | None = None) -> dict[str, Any]:
    """Tag the version ``version_id`` as a ref: ``name`` if given (a nickname - "omega",
    "banane"...), otherwise :func:`default_ref_name`. :class:`InvalidInput` for a name with a "/"
    (a ref is addressed as a single path segment), :class:`Conflict` for a name already used by a
    different ref or by a line of study (tags and branches share one namespace in Follow). Returns
    the ref as :func:`list_refs` shows it.
    """
    nickname = name.strip() if name else ""
    if "/" in nickname:
        raise InvalidInput("Le nom d'une ref ne peut pas contenir « / ».", code="invalid_ref_name")
    final_name = nickname or _unique_default_name(repo, default_ref_name(repo, version_id), version_id)
    try:
        repo.tag(final_name, at=version_id)
    except follow.FollowError as exc:
        raise Conflict(f"Le nom « {final_name} » est déjà pris par une autre version ou une piste.", code="ref_name_taken") from exc
    return next(entry for entry in list_refs(repo) if entry["version_id"] == version_id)


def ref_names_for(repo: "follow.Repository", version_id: str) -> list[str]:
    """Every ref name currently pointing at ``version_id`` - several nicknames can point at the
    same version (a Follow tag is just an entry in a name -> id dict)."""
    return sorted(name for name, target in repo.tags.items() if target == version_id)


def list_refs(repo: "follow.Repository") -> list[dict[str, Any]]:
    """Every ref in this microproject, newest first: one entry per tagged version (several
    nicknames on the same one collapse into a single entry, its ``names`` carrying all of them),
    with the line of study it was recorded on (``experiment_id``) and its X.Y.Z.
    """
    by_version: dict[str, list[str]] = {}
    for name, version_id in repo.tags.items():
        by_version.setdefault(version_id, []).append(name)

    entries = []
    for version_id, names in by_version.items():
        version = repo.get(version_id)
        entries.append(
            {
                "version_id": version_id,
                "experiment_id": version.branch,
                "names": sorted(names),
                "title": version.title,
                "status": display_status(version),
                "decision": version.conclusion.decision,
                "version": _version_for(repo, version_id),
                "created_at": version.created_at.isoformat(),
            }
        )
    entries.sort(key=lambda entry: entry["created_at"], reverse=True)
    return entries


def ref_graph(repo: "follow.Repository") -> dict[str, Any]:
    """``{refs, edges}`` : the refs, and one ``{from, to}`` edge (version ids) per path from a ref
    back to its nearest ref ancestor, whatever ordinary versions sit in between - condensed the
    same way :func:`spectre.plugins.experiments.lineage.condensed_edges` collapses branch tips, so a
    caller can navigate "from ref to ref" without drawing the whole lineage.
    """
    entries = list_refs(repo)
    edges = condensed_edges(repo, [repo.get(entry["version_id"]) for entry in entries])
    return {"refs": entries, "edges": [{"from": a, "to": b} for a, b in edges]}
