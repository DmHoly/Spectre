"""Ce que wafer_data sait dater pour la frise d'une plaque (``wafers.timeline.register_source``) : pour chaque type
de données PRISM par plaque qui a une colonne de date (eqe, pl, el_pattern...), les jours où elle a été mesurée et
combien de lignes chaque jour porte. Les types sont lus comme pour la fiche data (cache PRISM, ou la démo) ; un
type en échec est ignoré."""

from __future__ import annotations

import logging
from typing import Any

from ...kernel.errors import DomainError
from ..accounts.service import User
from ..characterization import service as characterization
from . import blocks
from .digest import _date_column, _day

log = logging.getLogger(__name__)

MAX_HOOKS = 8


def data_events(user: User, lasermark: str) -> list[dict[str, Any]]:  # noqa: ARG001 - la signature d'une source
    out: list[dict[str, Any]] = []
    seen = 0
    for entry in blocks.catalog():
        if not entry.dated or seen >= MAX_HOOKS:
            continue
        seen += 1
        try:
            result = characterization.query(entry.hook, {"wafer_names": [lasermark]})
        except DomainError as exc:
            log.info("frise de %s : %s non lu (%s)", lasermark, entry.hook, exc)
            continue
        at = _date_column(result.columns)
        if at is None or not result.rows:
            continue
        per_day: dict[str, int] = {}
        for row in result.rows:
            day = _day(row[at])
            if day:
                per_day[day] = per_day.get(day, 0) + 1
        for day, n in sorted(per_day.items()):
            out.append({
                "kind": "data",
                "at": day,
                "end": None,
                "precision": "day",
                "label": f"{entry.title} · {n} ligne{'s' if n > 1 else ''}",
                "detail": f"{entry.hook} · {result.source}",
                "source": f"PRISM {entry.hook}",
                "ref": {"detail": "data", "hook": entry.hook, "day": day, "rows": n},
            })
    return out
