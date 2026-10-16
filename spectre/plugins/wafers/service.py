"""Index des plaques : chaque entité physique suivie (un wafer, par son lasermark - ``sample_id``
dans ``Experiment.metadata["physical_tracking"]``) avec son emplacement, ses FDL (voir
:mod:`spectre.plugins.wafers.fdl`) et l'étude qui la suit - de quoi la retrouver depuis la barre de
recherche, et retracer son parcours d'une étude, voire d'un µprojet, à l'autre. Une plaque est
désignée par sa clé, :func:`wafer_key` : le lasermark sans casse ni séparateurs.

Seul l'état courant de chaque piste compte (sa pointe de branche, comme les autres vues des
entités). L'index d'un µprojet est gardé en mémoire et ne se reconstruit que si son dépôt Follow a
bougé : chaque commit réécrit ``refs.json`` et ajoute un fichier dans ``objects/`` (voir
:func:`_signature`) - taper dans la recherche ne relit donc pas tous les dépôts à chaque frappe.

**Fiches de plaque** (:mod:`.records`) : une plaque enregistrée pour elle-même, sans étude, est
dans l'index aussi (:func:`wafers`, :func:`passport`, avec ``records``) - ``count`` 0, ``latest``
``None``, et sa fiche sous ``record``.

**Visibilité** - une seule règle, pour les plaques comme pour les lots (qui la lisent ici) : chaque
étude qui suit une plaque est lue (:func:`occurrences`), quel que soit son µprojet ; un membre de ce
µprojet en voit tout, les autres n'en voient que le µprojet, le statut et les dates - ni titre, ni
lien, ni emplacement, ni FDL (:func:`experiment_payload`, :func:`occurrence_payload`), comme sur la
frise d'une thématique.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Iterable

from ...kernel.errors import Forbidden, NotFound
from ..accounts.service import User
from ..experiments.entities import compact
from ..experiments.repository import branch_tips, display_status, follow_repo_path, get_repository
from ..microprojects import service as microprojects
from ..microprojects.service import Microproject
from ..structures import kinds
from . import fdl as fdls

_CACHE: dict[str, tuple[tuple, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()


def wafer_key(lasermark: str | None) -> str:
    """La clé d'une plaque : son lasermark tel qu'on le compare (« w12-a3 » = « W12 A3 » = ``W12A3``)."""
    return compact(lasermark)


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


def _tracked_since(repo: Any, tip: Any) -> dict[str, str]:
    """Par clé de plaque, la date de la première version de la piste de ``tip`` qui la suit - quand
    elle y est entrée, plutôt que la dernière écriture sur l'étude (une mesure ajoutée au cahier
    d'une étude passée ne la rend pas plus « actuelle » pour la plaque)."""
    since: dict[str, str] = {}
    for version in repo.log(tip.id):  # de la pointe vers la racine
        if version.branch != tip.branch:
            continue
        for entry in version.metadata.get("physical_tracking", []):
            key = wafer_key(entry.get("sample_id"))
            if key:
                since[key] = version.created_at.isoformat()
    return since


def _build(slug: str) -> list[dict[str, Any]]:
    repo = get_repository(slug)
    entries: list[dict[str, Any]] = []
    for tip in branch_tips(repo):
        labels = tip.metadata.get("campaign_labels") or []
        campaign = tip.structure_type == kinds.ProcessLot.registry_key()
        since = _tracked_since(repo, tip)
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
                    "experiment": {
                        "id": tip.branch,  # la piste (lien vers la fiche)
                        "version_id": tip.id,  # la version qui suit la plaque aujourd'hui (pour en partir)
                        "title": tip.title,
                        "status": display_status(tip),
                        "updated_at": tip.created_at.isoformat(),
                        "tracked_since": since.get(wafer_key(entry.get("sample_id"))) or tip.created_at.isoformat(),
                        "campaign": campaign,
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


# --- visibilité --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Occurrence:
    """Une étude (la pointe d'une piste) qui suit une plaque, et si le lecteur est membre de son
    µprojet. ``entry`` est la ligne de l'index, entière : ne la montrer que par les fonctions
    ci-dessous."""

    microproject: Microproject
    entry: dict[str, Any]
    member: bool

    @property
    def key(self) -> str:
        return wafer_key(self.entry.get("sample_id"))

    @property
    def experiment_id(self) -> str:
        return self.entry["experiment"]["id"]

    @property
    def updated_at(self) -> str:
        return self.entry["experiment"]["updated_at"]


def microproject_for(user: User, slug: str) -> Microproject:
    """Le µprojet ``slug``, où ``user`` doit avoir un rôle (:func:`microprojects.access`) pour y
    lire les plaques en entier (404 s'il n'existe pas, 403 sinon)."""
    try:
        microproject = microprojects.get_by_slug(slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise NotFound(f"µprojet {slug!r} introuvable") from exc
    if microprojects.effective_role(user, microproject) is None:
        raise Forbidden("Vous n'êtes pas membre de ce µprojet.")
    return microproject


def occurrences(user: User, *, keys: Iterable[str] | None = None, microproject: Microproject | None = None) -> list[Occurrence]:
    """Chaque étude qui suit une plaque - de tous les µprojets, ou du seul ``microproject`` ;
    seulement les plaques de ``keys`` (des clés ou des lasermarks), si elles sont données - vue par
    ``user`` (« membre » : quiconque y a un rôle, :func:`microprojects.access`)."""
    selected = [microproject] if microproject else microprojects.list_all()
    found_access = microprojects.accesses(user, selected)
    member_of = {mp_id for mp_id, access in found_access.items() if access.role is not None}
    wanted = None if keys is None else {wafer_key(key) for key in keys} - {""}
    found = []
    for mp in selected:
        for entry in entries_for(mp.slug):
            if wanted is None or wafer_key(entry.get("sample_id")) in wanted:
                found.append(Occurrence(mp, entry, mp.id in member_of))
    return found


def microproject_ref(microproject: Microproject) -> dict[str, Any]:
    return {"slug": microproject.slug, "code": microproject.code, "name": microproject.name}


def experiment_payload(occurrence: Occurrence, public: dict[str, Any]) -> dict[str, Any]:
    """L'étude d'une occurrence telle que le lecteur la voit : son µprojet et ``public`` (son
    statut, ses dates) pour tous ; son id (la piste), sa version actuelle, son titre et si c'est
    une campagne pour les membres."""
    experiment = occurrence.entry["experiment"]
    member = (
        {"id": experiment["id"], "version_id": experiment["version_id"], "title": experiment["title"], "campaign": experiment["campaign"]}
        if occurrence.member
        else {}
    )
    return {"microproject": microproject_ref(occurrence.microproject), "member": occurrence.member, **public, **member}


def occurrence_payload(occurrence: Occurrence) -> dict[str, Any]:
    """Une étude qui suit une plaque, telle que le lecteur la voit : où la plaque a été rangée, ses
    FDL et la variante qu'elle porte dans une campagne pour les membres seulement."""
    entry = occurrence.entry
    public = {
        "status": entry["experiment"]["status"],
        "updated_at": occurrence.updated_at,
        "tracked_since": entry["experiment"]["tracked_since"],  # quand la plaque est entrée dans l'étude
    }
    payload = {
        "lasermark": entry.get("sample_id"),
        "entity_index": entry["entity_index"],
        "experiment": experiment_payload(occurrence, public),
    }
    if occurrence.member:
        payload.update(location=entry["location"], fdl=entry["fdl"], variant=entry["variant"])
    return payload


# --- plaques ------------------------------------------------------------------------------------


def unique(values: Iterable[Any]) -> list[Any]:
    found: list[Any] = []
    for value in values:
        if value and value not in found:
            found.append(value)
    return found


_unique = unique


def _latest_first(found: Iterable[Occurrence]) -> list[Occurrence]:
    return sorted(found, key=lambda o: o.updated_at, reverse=True)


def latest_members(found: Iterable[Occurrence]) -> dict[str, Occurrence]:
    """Par clé de plaque, l'étude la plus récente dont le lecteur est membre - celle dont une plaque
    montre la structure ; une plaque suivie seulement par des études qu'il ne lit pas n'y est pas."""
    latest: dict[str, Occurrence] = {}
    for occurrence in _latest_first(o for o in found if o.member and o.key):
        latest.setdefault(occurrence.key, occurrence)
    return latest


def _wafer_payload(
    key: str, found: list[Occurrence], record: dict[str, Any] | None, line: dict[str, Any] | None = None, names: list[str] | None = None
) -> dict[str, Any]:
    members = [o for o in found if o.member]
    line = line or {}
    return {
        "key": key,
        "lasermark": found[0].entry["sample_id"] if found else record["lasermark"],
        "count": len(found),
        "microprojects": _unique(microproject_ref(o.microproject) for o in found),
        "latest": occurrence_payload(found[0]) if found else None,
        "fdl": _unique(value for o in members for value in o.entry["fdl"]),
        "locations": _unique(o.entry["location"] for o in members),
        "record": record,  # sa fiche de plaque (records), ou None
        "line_fdl": list(line.get("fdls") or []),  # les FDL que la vie en ligne lui connaît (tracking)
        "lot_name": line.get("lot_name"),  # son lot JIRA, lu en ligne
        "aliases": list(names or []),  # ses autres noms (links : XX devenue YY)
    }


def _queries(q: str | Iterable[str]) -> list[str]:
    """Les textes cherchés : un seul, ou plusieurs lasermarks à la fois - sans les vides."""
    values = [q] if isinstance(q, str) else list(q)
    return [value for value in values if value.strip()]


def _alias_rank(queries: list[str], key: str, names: list[str]) -> tuple[int | None, str | None]:
    """Le rang d'une plaque pour ``queries`` : par sa clé, sinon - juste après - par l'un de ses
    autres noms (celui qui a répondu est rendu)."""
    direct = _q_rank(queries, key)
    if direct is not None:
        return 2 * direct, None
    best: tuple[int | None, str | None] = (None, None)
    for name in names:
        rank = _q_rank(queries, wafer_key(name))
        if rank is not None and (best[0] is None or 2 * rank + 1 < best[0]):
            best = (2 * rank + 1, name)
    return best


def _q_rank(queries: list[str], key: str) -> int | None:
    """Exact first, then starting with what was typed, then containing it - the best of the
    queries, None when none matches."""
    ranks = []
    for query in queries:
        wanted = wafer_key(query)
        if not wanted:
            continue
        if key == wanted:
            ranks.append(0)
        elif key.startswith(wanted):
            ranks.append(1)
        elif wanted in key:
            ranks.append(2)
    return min(ranks) if ranks else None


def wafers(
    found: Iterable[Occurrence],
    *,
    q: str | Iterable[str] = "",
    fdl: str = "",
    records: dict[str, dict[str, Any]] | None = None,
    line: dict[str, dict[str, Any]] | None = None,
    aliases: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Les plaques de ces occurrences et des fiches ``records``, une par clé (chacune avec ses
    études, la plus récente d'abord) - celles dont le lasermark correspond à ``q`` (un texte, ou
    plusieurs lasermarks ; le lasermark exact d'abord, puis les plaques dont un autre nom -
    ``aliases``, une plaque renommée - correspond : ``matched_alias``), qui portent une FDL
    correspondant à ``fdl`` (celles des études chez les membres seulement, et celles que la vie en
    ligne lui connaît - ``line``, publique comme sa page), ou toutes."""
    line = line or {}
    aliases = aliases or {}
    queries = _queries(q)
    by_key: dict[str, list[Occurrence]] = {}
    for occurrence in found:
        if occurrence.key:
            by_key.setdefault(occurrence.key, []).append(occurrence)
    for key in records or {}:
        by_key.setdefault(key, [])
    ranked = []
    for key, group in by_key.items():
        q_rank, matched = _alias_rank(queries, key, aliases.get(key, [])) if queries else (0, None)
        facts = line.get(key) or {}
        values = [value for o in group if o.member for value in o.entry["fdl"]] + list(facts.get("fdls") or [])
        fdl_rank = fdls.best_rank(fdl, values) if fdl.strip() else 0
        if q_rank is not None and fdl_rank is not None:
            payload = _wafer_payload(key, _latest_first(group), (records or {}).get(key), facts, aliases.get(key))
            payload["matched_alias"] = matched
            ranked.append(((q_rank, fdl_rank, key), payload))
    return [payload for _rank, payload in sorted(ranked, key=lambda item: item[0])]


def passport(
    lasermark: str, found: Iterable[Occurrence], record: dict[str, Any] | None = None, line: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Tout ce qu'on sait d'une plaque : chaque étude qui la suit (la plus récente d'abord), où elle
    a été rangée et ses FDL (chez les membres), sa fiche de plaque s'il y en a une - ce que montre
    sa page. Une plaque qu'aucune étude ne suit (encore) n'est pas une erreur : la page l'explique."""
    key = wafer_key(lasermark)
    group = _latest_first(o for o in found if o.key == key)
    members = [o for o in group if o.member]
    return {
        "key": key,
        "lasermark": group[0].entry["sample_id"] if group else record["lasermark"] if record else lasermark.strip(),
        "occurrences": [occurrence_payload(o) for o in group],
        "fdl": _unique(value for o in members for value in o.entry["fdl"]),
        "microprojects": _unique(microproject_ref(o.microproject) for o in group),
        "last_location": next((o.entry["location"] for o in members if o.entry["location"]), None),
        "record": record,
        "line_fdl": list((line or {}).get("fdls") or []),  # les FDL que la vie en ligne lui connaît
        "lot_name": (line or {}).get("lot_name"),
    }
