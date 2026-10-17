"""Les données d'une analyse, face à la référence : pour chaque KPI comparé, une boîte à moustaches par plaque
(sa mesure la plus récente, quand le type de données a une date) et l'écart de sa médiane à celle de la
référence. Calcul à la demande, jamais gardé : les lignes viennent du cache par plaque de PRISM, comme les KPI
suivis d'un projet (:mod:`spectre.plugins.kpi_tracking.service`), dont ce module reprend la lecture et les
statistiques.

Ce qu'on propose de comparer : n'importe quelle colonne d'un type de données PRISM par plaque (ses colonnes de
KPI d'abord) et, d'abord, les KPI que suivent déjà les projets corporate des plaques de l'analyse.

Les blocs libres de l'analyse (:func:`blocks`) : les blocs de la fiche data (plugin wafer_data) choisis dans
l'analyse, calculés sur chacune de ses plaques - par :func:`wafer_data.service.gather`, qui relit ou calcule
leurs résumés comme pour la fiche d'une plaque.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from ...kernel.errors import DomainError, InvalidInput, NotFound
from ..accounts.service import User
from ..areas import service as areas
from ..kpi_tracking import service as kpi_tracking
from ..wafer_data import blocks as wafer_blocks
from ..wafer_data import service as wafer_data
from ..wafers import service as wafers
from .service import column_catalog, kpi_title

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
    catalogue = {key: found["entry"] for key, found in column_catalog().items()} if analysis["kpis"] else {}
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
            result.update(status="unavailable", message="Cette colonne n'est plus au catalogue PRISM.")
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
    """Ce qu'on peut comparer : ``catalog`` (toutes les colonnes des types de données PRISM par plaque - ``kpi``
    vrai pour les colonnes de KPI, ``type`` quand la fiche data le connaît -, sans celles qu'on sait n'être pas des
    scalaires) et ``suggested`` - les KPI que suivent les projets corporate des plaques de l'analyse (``area`` : le
    projet), sans ceux que l'analyse compare déjà."""
    catalog = [
        {**asdict(found["entry"]), "key": key, "type": found["type"], "sure": found["sure"]}
        for key, found in column_catalog().items()
        if found["entry"].kpi or not found["sure"] or found["type"] == "number"
    ]
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


def blocks(user: User, analysis: dict[str, Any], *, refresh: bool = False) -> dict[str, Any]:
    """Les blocs libres de l'analyse, chacun calculé sur chaque plaque, dans l'ordre de l'analyse : ``{source,
    blocks: [{index, kind, kind_label, title, label, hook, hook_title, unit, units, config, available, wafers: [{key,
    lasermark, status, message, computed_at, data}]}]}``. Les images se lisent une à une par :func:`block_image`."""
    if not analysis["blocks"]:
        return {"source": None, "blocks": []}
    entries = {h.hook: h for h in wafer_blocks.catalog()}
    chosen = [wafer_data.free_block(i, b["kind"], b["hook"], b["config"], b["label"]) for i, b in enumerate(analysis["blocks"])]
    live = [b for b in chosen if b.from_pattern or b.hook in entries]
    pairs = [(w["key"], w["lasermark"]) for w in analysis["wafers"]]
    stored, sources = wafer_data.gather(pairs, live, refresh=refresh)
    out = []
    for block in chosen:
        available = block in live
        per_wafer = []
        for key, lasermark in pairs:
            found = stored[key].get(block.sig) if available else {"status": "error", "message": "Ce type de données n'est plus dans PRISM.", "payload": None}
            url = lambda n, key=key, index=block.id: f"/api/analyses/{analysis['id']}/blocks/{index}/images/{key}/{n}"
            shown = wafer_data.block_payload(block, found, wafer=key, entries=entries, image_url=url)
            per_wafer.append({"key": key, "lasermark": lasermark, **{name: shown[name] for name in ("status", "message", "computed_at", "data")}})
        shown = wafer_data.block_payload(block, None, wafer="", entries=entries)
        out.append(
            {
                "index": block.id,
                **{name: shown[name] for name in ("kind", "kind_label", "title", "label", "hook", "hook_title", "unit", "units", "config")},
                "available": available,
                "wafers": per_wafer,
            }
        )
    return {"source": wafer_data.source_of(sources), "blocks": out}


def block_image(analysis: dict[str, Any], index: int, wafer_key: str, image: int):
    """Le fichier de la ``image``-ième image du bloc libre ``index`` sur une plaque de l'analyse (404 sinon)."""
    if not 0 <= index < len(analysis["blocks"]) or wafer_key not in {w["key"] for w in analysis["wafers"]}:
        raise NotFound("Image inconnue pour cette analyse.")
    b = analysis["blocks"][index]
    return wafer_data.stored_image(wafer_data.free_block(index, b["kind"], b["hook"], b["config"], b["label"]), wafer_key, image)
