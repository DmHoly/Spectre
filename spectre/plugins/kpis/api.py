"""Les tendances d'un projet corporate : les onglets KPI de sa page et la série mensuelle de chacun
(voir :mod:`spectre.plugins.kpis.service`, le registre des KPI).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as management
from ..areas.service import ManagementArea, ManagementAreaNotFoundError
from . import service as trends

router = APIRouter(prefix="/api/management", tags=["kpis"])


def _get_area(slug: str) -> ManagementArea:
    try:
        return management.get_by_slug(slug)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def _kpi_payload(kpi: trends.KpiDefinition) -> dict:
    return {
        "key": kpi.key,
        "label": kpi.label,
        "unit": kpi.unit,
        "description": kpi.description,
        "better": kpi.better,
        "source": kpi.source,
        "hook": kpi.hook,
        "status": kpi.status,
        "variants": [{"key": v.key, "label": v.label, "unit": v.unit} for v in kpi.variants],
    }


def _point_payload(point: trends.TrendPoint) -> dict:
    payload = {"period": point.period, "value": point.value}
    if point.study:
        payload["study"] = point.study
        payload["label"] = point.label
    return payload


@router.get("/{slug}/tendances")
def list_trends(slug: str, user: User = Depends(current_user)) -> dict:
    """The KPI tabs available for this project - cheap (no data); each tab then loads its own
    series lazily, so a slow PRISM-backed KPI never delays the page."""
    _get_area(slug)
    return {"kpis": [_kpi_payload(k) for k in trends.list_kpis()]}


def _get_kpi(kpi_key: str) -> trends.KpiDefinition:
    try:
        return trends.get_kpi(kpi_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"KPI {kpi_key!r} inconnu") from exc


@router.get("/{slug}/tendances/{kpi_key}")
def get_trend(
    slug: str,
    kpi_key: str,
    mois: int = Query(12, ge=1, le=60),
    variante: str | None = Query(None),
    user: User = Depends(current_user),
) -> dict:
    area = _get_area(slug)
    kpi = _get_kpi(kpi_key)
    try:
        variant = kpi.variant(variante)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"variante {variante!r} inconnue pour {kpi_key!r}") from exc
    result = trends.series(kpi_key, area, mois, variant.key if variant else None)
    payload = {
        **_kpi_payload(kpi),
        "status": result.status,
        "message": result.message,
        "target": result.target,
        "periods": trends.month_periods(mois),
        "points": [_point_payload(pt) for pt in result.points],
        "variant": variant.key if variant else None,
    }
    if variant:
        payload["unit"] = variant.unit or kpi.unit
        payload["description"] = variant.description or kpi.description
        payload["variant_label"] = variant.label
    return payload
