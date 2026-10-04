"""Les plaques dans la recherche de la barre du haut (:mod:`spectre.plugins.search`) : par lasermark
(« W12-A3 », séparateurs et casse ignorés : sa page, toutes les études qui la suivent) et, dès qu'on
tape un chiffre, par FDL (« 1234 », « FDL-1234 ») : les études dont une plaque la porte - chez les
membres seulement, comme toute FDL (:mod:`.service`)."""

from __future__ import annotations

import re
from urllib.parse import quote

from ..accounts.service import User
from ..search.service import SearchHit, SearchProvider, register_provider
from . import fdl, service

WAFER_LIMIT = 6
FDL_LIMIT = 8


def wafer_url(lasermark: str) -> str:
    return f"/plaques/{quote(lasermark, safe='')}"


def _wafers(query: str, user: User) -> list[SearchHit]:
    if len(service.wafer_key(query)) < 2:
        return []
    hits = []
    for wafer in service.wafers(service.occurrences(user), q=query)[:WAFER_LIMIT]:
        latest = wafer["latest"]["experiment"]
        codes = [m["code"] or m["name"] for m in wafer["microprojects"]]
        hits.append(
            SearchHit(
                label=wafer["lasermark"],
                detail=f"{wafer['count']} études" if wafer["count"] > 1 else latest.get("title", ""),
                badge=", ".join(codes[:2]) + ("…" if len(codes) > 2 else ""),
                url=wafer_url(wafer["lasermark"]),
            )
        )
    return hits


def _fdls(query: str, user: User) -> list[SearchHit]:
    found = []
    for occurrence in service.occurrences(user):
        if not occurrence.member:
            continue
        for value in occurrence.entry["fdl"]:
            rank = fdl.rank(query, value)
            if rank is not None:
                found.append((rank, value, occurrence))
    found.sort(key=lambda hit: (hit[0], hit[1], hit[2].entry["experiment"]["title"]))
    hits = []
    for _rank, value, occurrence in found[:FDL_LIMIT]:
        lasermark = occurrence.entry.get("sample_id")
        mp = occurrence.microproject
        hits.append(
            SearchHit(
                label=value,
                detail=occurrence.entry["experiment"]["title"] + (f" · {lasermark}" if lasermark else ""),
                badge=mp.code or mp.name,
                url=f"/microprojets/{quote(mp.slug, safe='')}/experiences/{quote(occurrence.experiment_id, safe='')}",
            )
        )
    return hits


def _looks_like_an_fdl(query: str) -> bool:
    """« 1234 », « FDL 12 » : une FDL d'abord."""
    return re.fullmatch(r"\s*(fdl)?[\s_\-#:]*\d+\s*", query, re.IGNORECASE) is not None


register_provider(SearchProvider(type="wafer", search=_wafers, order=30))
register_provider(SearchProvider(type="fdl", search=_fdls, order=40, leads=_looks_like_an_fdl))
