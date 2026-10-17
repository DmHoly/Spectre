"""Les données d'une analyse, face à la référence : pour chaque KPI comparé, une boîte à moustaches par plaque
(sa mesure la plus récente, quand le type de données a une date) et l'écart de sa médiane à celle de la
référence. Calcul à la demande, jamais gardé : les lignes viennent du cache par plaque de PRISM, comme les KPI
suivis d'un projet (:mod:`spectre.plugins.kpi_tracking.service`), dont ce module reprend la lecture et les
statistiques.

Ce qu'on propose de comparer : le catalogue des KPI de PRISM et, d'abord, les KPI que suivent déjà les projets
corporate des plaques de l'analyse.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from ...kernel.errors import DomainError, InvalidInput
from ..accounts.service import User
from ..areas import service as areas
from ..kpi_tracking import service as kpi_tracking
from ..wafers import service as wafers
from .service import kpi_title

log = logging.getLogger(__name__)


def _delta(median: float | None, reference: float | None) -> dict[str, float | None] | None:
    """L'écart d'une médiane à celle de la référence : absolu, et relatif (``None`` face à une référence nulle)."""
    if median is None or reference is None:
        return None
    absolute = median - reference
    return {"absolute": absolute, "relative": absolute / abs(reference) if reference else None}


def _groups(analysis: dict[str, Any], by_wafer: dict[str, dict[str | None, list[float]]]) -> list[dict[str, Any]]:
    """Une boîte par plaque, dans l'ordre de l'analyse (la référence d'abord) : sa mesure la plus récente."""
    groups = []
    for wafer in analysis["wafers"]:
        days = by_wafer.get(wafer["key"]) or {}
        dated = sorted(d for d in days if d)
        day = dated[-1] if dated else None
        computed = kpi_tracking.box_stats(days.get(day) or [])
        groups.append(
            {
                "key": wafer["key"],
                "wafer": wafer["lasermark"],
                "date": day,
                "dates": len(dated),  # combien de jours de mesure : la boîte ne montre que le dernier
                "stats": asdict(computed[0]) if computed else None,
                "outliers": computed[1] if computed else [],
            }
        )
    reference = groups[0]["stats"]["median"] if groups and groups[0]["stats"] else None
    for group in groups:
        group["delta"] = _delta(group["stats"]["median"] if group["stats"] else None, reference) if group is not groups[0] else None
    return groups


def kpis(analysis: dict[str, Any], *, refresh: bool = False) -> dict[str, Any]:
    """``{source, kpis: [{hook, column, title, unit, hook_title, better, filters, status, message, groups}]}`` ;
    ``status`` : ok, error (la base n'a pas répondu, une colonne a disparu) ou unavailable (plus au catalogue)."""
    catalogue = {k.key: k for k in kpi_tracking.catalog()} if analysis["kpis"] else {}
    lasermarks = [w["lasermark"] for w in analysis["wafers"]]
    queries: dict[str, tuple[str, list[str], list[list[Any]]] | Exception] = {}
    sources: set[str] = set()
    results = []
    for kpi in analysis["kpis"]:
        entry = catalogue.get(f"{kpi['hook']}:{kpi['column']}")
        result = {
            **{name: kpi[name] for name in ("hook", "column", "label", "filters", "better")},
            "title": kpi_title(kpi),
            "unit": entry.unit if entry else "",
            "hook_title": entry.hook_title if entry else kpi["hook"],
            "status": "ok",
            "message": "",
            "groups": [],
        }
        results.append(result)
        if entry is None:
            result.update(status="unavailable", message="Ce KPI n'est plus au catalogue PRISM.")
            continue
        if kpi["hook"] not in queries:
            try:
                queries[kpi["hook"]] = kpi_tracking.query_hook(kpi["hook"], lasermarks, refresh)
            except Exception as exc:  # une base injoignable ne prive pas des autres types de données
                queries[kpi["hook"]] = exc
        outcome = queries[kpi["hook"]]
        if isinstance(outcome, Exception):
            if not isinstance(outcome, DomainError):
                log.exception("Analyse %s, KPI %s:%s : calcul impossible", analysis["id"], kpi["hook"], kpi["column"], exc_info=outcome)
            message = str(outcome) if isinstance(outcome, DomainError) else "Calcul impossible pour le moment : l'erreur a été journalisée sur le serveur."
            result.update(status="error", message=message)
            continue
        source, columns, rows = outcome
        sources.add(source)
        try:
            by_wafer = kpi_tracking.values_by_wafer(columns, rows, kpi["column"], tuple(kpi["filters"]))
        except InvalidInput as exc:
            result.update(status="error", message=str(exc))
            continue
        result["groups"] = _groups(analysis, by_wafer)
    return {"source": sorted(sources)[0] if len(sources) == 1 else ("mixed" if sources else None), "kpis": results}


def kpi_choices(user: User, analysis: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'on peut comparer : ``catalog`` (toutes les colonnes de KPI de PRISM, par type de données) et
    ``suggested`` - les KPI que suivent les projets corporate des plaques de l'analyse (``area`` : le projet),
    sans ceux que l'analyse compare déjà."""
    catalog = [{**asdict(k), "key": k.key} for k in kpi_tracking.catalog()]
    found = wafers.occurrences(user, keys=[w["key"] for w in analysis["wafers"]])
    area_ids = list(dict.fromkeys(o.microproject.management_area_id for o in found if o.microproject.management_area_id))
    chosen = {(k["hook"], k["column"], repr(k["filters"])) for k in analysis["kpis"]}
    suggested = []
    for area_id in area_ids:
        area = areas.get_by_id(area_id)
        for tracked in kpi_tracking.list_tracked(area):
            if (tracked.hook, tracked.column, repr(list(tracked.filters))) in chosen:
                continue
            goal = (tracked.goal or {}).get("mode")
            suggested.append(
                {
                    "hook": tracked.hook,
                    "column": tracked.column,
                    "label": tracked.label,
                    "filters": list(tracked.filters),
                    "better": {"max": "high", "min": "low"}.get(goal),
                    "title": tracked.title,
                    "area": {"slug": area.slug, "name": area.name},
                }
            )
    return {"catalog": catalog, "suggested": suggested}
