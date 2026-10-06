"""Les lots dans la recherche de la barre du haut (:mod:`spectre.plugins.search`) : par code ou
intitulé, ou par l'un de leurs wafers - visibles de tous, comme les lots."""

from __future__ import annotations

from urllib.parse import quote

from ..accounts.service import User
from ..search.service import SearchHit, SearchProvider, register_provider
from . import service

LIMIT = 6
STATUS_LABELS = {"planned": "en préparation", "wip": "en cours", "hold": "en pause", "done": "sorti", "cancelled": "annulé"}


def _lots(query: str, user: User) -> list[SearchHit]:
    return [
        SearchHit(
            label=lot.code,
            detail=f"contient {wafer}" if wafer else lot.title or "Lot",
            badge=" · ".join(part for part in (lot.priority, STATUS_LABELS[lot.status]) if part),
            url=f"/lots/{quote(lot.code, safe='')}",
        )
        for lot, wafer in service.search(query, limit=LIMIT)
    ]


register_provider(SearchProvider(type="lot", plugin="lots", search=_lots, order=20))
