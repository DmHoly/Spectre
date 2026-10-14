"""Les plaques dans le comparateur (:mod:`spectre.plugins.comparator`) : le jeton
``wafer:<lasermark>`` désigne la structure qu'a vue une plaque - celle de la dernière étude de vos
µprojets qui la suit (sa variante dans une campagne, sa ligne dans un split déclaré) ; la saisie
d'un lasermark propose les plaques suivies (séparateurs et casse ignorés, comme la recherche)."""

from __future__ import annotations

from typing import Any

from ...kernel.errors import Forbidden, NotFound
from ..accounts.service import User
from ..comparator.service import Compared, ItemSource, register_source, study_rows
from . import service


def _resolve(user: User, lasermark: str) -> list[Compared]:
    found = service.occurrences(user, keys=[lasermark])
    if not found:
        raise NotFound(f"Aucune étude ne suit la plaque « {lasermark} ».", code="wafer_not_tracked")
    latest = service.latest_members(found).get(service.wafer_key(lasermark))
    if latest is None:
        raise Forbidden("Les études qui suivent cette plaque sont dans des µprojets dont vous n'êtes pas membre.")
    entry = latest.entry
    rows = study_rows(user, latest.microproject.slug, latest.experiment_id, entry["experiment"]["version_id"], entry["entity_index"])
    sample = entry.get("sample_id") or lasermark
    for row in rows:
        # une étude simple se nomme par son titre : il passe sous le lasermark
        row.sublabel = row.sublabel or row.label
        row.item, row.source, row.label, row.wafers = f"wafer:{sample}", "wafer", sample, [sample]
    return rows[:1]


def _search(user: User, q: str, limit: int) -> list[dict[str, Any]]:
    if len(service.wafer_key(q)) < 2:
        return []
    candidates = []
    for wafer in service.wafers(service.occurrences(user), q=q):
        latest = wafer["latest"]
        if not latest["experiment"].get("member"):
            continue
        candidates.append(
            {
                "item": f"wafer:{wafer['lasermark']}",
                "source": "wafer",
                "label": wafer["lasermark"],
                "sublabel": " · ".join(part for part in (latest["experiment"].get("title"), latest["experiment"]["microproject"]["name"]) if part),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


register_source(ItemSource("wafer", _resolve, _search, plugin="wafers", order=10))
