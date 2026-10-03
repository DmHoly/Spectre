"""Index des plaques : chaque entité physique suivie (un wafer, par son lasermark - ``sample_id``
dans ``Experiment.metadata["physical_tracking"]``) avec son emplacement, ses FDL (voir
:mod:`spectre.plugins.wafers.fdl`) et l'étude qui la suit - de quoi la retrouver depuis la barre de
recherche, et retracer son parcours d'une étude, voire d'un µprojet, à l'autre.

Seul l'état courant de chaque piste compte (sa pointe de branche, comme les autres vues des
entités). L'index d'un µprojet est gardé en mémoire et ne se reconstruit que si son dépôt Follow a
bougé : chaque commit réécrit ``refs.json`` et ajoute un fichier dans ``objects/`` (voir
:func:`_signature`) - taper dans la recherche ne relit donc pas tous les dépôts à chaque frappe.
"""

from __future__ import annotations

import threading
from typing import Any, Iterable

from ..experiments.entities import compact, entities_for
from ..experiments.repository import branch_tips, display_status, follow_repo_path, get_repository
from ..microprojects import service as microprojects

_CACHE: dict[str, tuple[tuple, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()


def _signature(slug: str) -> tuple | None:
    repo_dir = follow_repo_path(slug)
    refs = repo_dir / "refs.json"
    objects = repo_dir / "objects"
    try:
        refs_stat = refs.stat()
    except FileNotFoundError:
        return None
    objects_mtime = objects.stat().st_mtime_ns if objects.exists() else 0
    return (refs_stat.st_mtime_ns, refs_stat.st_size, objects_mtime)


def _build(slug: str) -> list[dict[str, Any]]:
    repo = get_repository(slug)
    entries: list[dict[str, Any]] = []
    for tip in branch_tips(repo):
        labels = tip.metadata.get("campaign_labels") or []
        for index, entry in enumerate(tip.metadata.get("physical_tracking", [])):
            if not entry.get("sample_id") and not entry.get("fdl"):
                continue
            entries.append(
                {
                    "sample_id": entry.get("sample_id"),
                    "location": entry.get("location"),
                    "fdl": list(entry.get("fdl") or []),
                    "entity_index": index,
                    "variant": labels[index] if index < len(labels) else None,
                    "experience": {
                        "id": tip.branch,  # la piste (lien vers la fiche)
                        "title": tip.title,
                        "status": display_status(tip),
                        "updated_at": tip.created_at.isoformat(),
                    },
                }
            )
    return entries


def entries_for(slug: str) -> list[dict[str, Any]]:
    """Every tracked plate of a microproject's current lines of study, from the cache when its
    repository hasn't changed since."""
    signature = _signature(slug)
    if signature is None:
        return []
    key = str(follow_repo_path(slug))  # le dépôt lui-même, pas seulement son nom
    cached = _CACHE.get(key)
    if cached and cached[0] == signature:
        return cached[1]
    entries = _build(slug)
    with _LOCK:
        _CACHE[key] = (signature, entries)
    return entries


def visible_entries(user_id: int) -> Iterable[tuple[Any, dict[str, Any]]]:
    """``(microproject, entry)`` for every plate in the microprojects ``user_id`` is a member of -
    an experience (and so its plates) is only ever visible to its microproject's members."""
    for microproject, _role in microprojects.list_for_user(user_id):
        for entry in entries_for(microproject.slug):
            yield microproject, entry


def _microproject_ref(microproject: Any) -> dict[str, Any]:
    return {"slug": microproject.slug, "code": microproject.code, "name": microproject.name}


def _occurrence(microproject: Any, entry: dict[str, Any]) -> dict[str, Any]:
    return {**entry, "microproject": _microproject_ref(microproject)}


def search(query: str, rows: Iterable[tuple[Any, dict[str, Any]]], *, limit: int = 6) -> list[dict[str, Any]]:
    """Plates whose lasermark matches ``query`` - exact first, then starting with it, then
    containing it - one result per plate, with the studies that follow it (most recent first)."""
    wanted = compact(query)
    if len(wanted) < 2:
        return []
    plates: dict[str, dict[str, Any]] = {}
    for microproject, entry in rows:
        key = compact(entry.get("sample_id"))
        if not key:
            continue
        if key == wanted:
            rank = 0
        elif key.startswith(wanted):
            rank = 1
        elif wanted in key:
            rank = 2
        else:
            continue
        plate = plates.setdefault(key, {"sample_id": entry["sample_id"], "rank": rank, "occurrences": []})
        plate["occurrences"].append(_occurrence(microproject, entry))
    results = []
    for plate in sorted(plates.values(), key=lambda p: (p["rank"], p["sample_id"])):
        occurrences = sorted(plate["occurrences"], key=lambda o: o["experience"]["updated_at"], reverse=True)
        codes: list[str] = []
        for o in occurrences:
            label = o["microproject"]["code"] or o["microproject"]["name"]
            if label not in codes:
                codes.append(label)
        results.append(
            {
                "sample_id": plate["sample_id"],
                "count": len(occurrences),
                "microprojects": codes,
                "latest": {"id": occurrences[0]["experience"]["id"], "title": occurrences[0]["experience"]["title"], "microproject": occurrences[0]["microproject"]},
            }
        )
    return results[:limit]


def plate_history(lasermark: str, rows: Iterable[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
    """Everything about one plate: every study that follows it (most recent first), where it was
    put, its FDLs - what its own page shows."""
    wanted = compact(lasermark)
    occurrences = sorted(
        (_occurrence(microproject, entry) for microproject, entry in rows if wanted and compact(entry.get("sample_id")) == wanted),
        key=lambda o: o["experience"]["updated_at"],
        reverse=True,
    )
    fdl: list[str] = []
    microproject_refs: list[dict[str, Any]] = []
    for o in occurrences:
        for value in o["fdl"]:
            if value not in fdl:
                fdl.append(value)
        if o["microproject"] not in microproject_refs:
            microproject_refs.append(o["microproject"])
    location = next((o["location"] for o in occurrences if o["location"]), None)
    return {
        "sample_id": occurrences[0]["sample_id"] if occurrences else lasermark.strip(),
        "occurrences": occurrences,
        "fdl": fdl,
        "microprojects": microproject_refs,
        "last_location": location,
    }


def entity_history_for_microproject(repo: Any, tips: list[Any]) -> dict[str, list[str]]:
    """Every distinct sample_id/location/FDL already used anywhere on the microproject's current branch
    tips - not the full commit history (a superseded intermediate version's entities don't
    surface), the same "current state, not every version" scope
    :func:`spectre.plugins.experiments.entities.entities_for` already works at. Meant to feed an
    autocomplete on the physical-entities editor so a user typing a sample id or location sees
    what's already in use elsewhere in the microproject, rather than re-typing a slightly different
    spelling of the same thing.
    """
    sample_ids: set[str] = set()
    locations: set[str] = set()
    fdls: set[str] = set()
    for tip in tips:
        for entry in entities_for(tip):
            if entry["sample_id"]:
                sample_ids.add(entry["sample_id"])
            if entry["location"]:
                locations.add(entry["location"])
            fdls.update(entry.get("fdl", []))
    return {"sample_ids": sorted(sample_ids), "locations": sorted(locations), "fdls": sorted(fdls)}
