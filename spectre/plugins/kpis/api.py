"""Les tendances d'un projet corporate : les onglets KPI de sa page et la série mensuelle de chacun
(voir :mod:`spectre.plugins.kpis.service`, le registre des KPI).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from . import service as trends

router = APIRouter(prefix="/api/areas", tags=["kpis"])


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


@router.get("/{area_slug}/kpis")
def list_kpis(area_slug: str, user: User = Depends(current_user)) -> list[dict]:
    """The KPI tabs available for this project - cheap (no data); each tab then loads its own
    series lazily, so a slow PRISM-backed KPI never delays the page."""
    areas.get_by_slug(area_slug)
    return [_kpi_payload(k) for k in trends.list_kpis()]


@router.get("/{area_slug}/kpis/{kpi_key}")
def get_kpi_series(
    area_slug: str,
    kpi_key: str,
    months: int = Query(12, ge=1, le=60),
    variant: str | None = None,
    user: User = Depends(current_user),
) -> dict:
    """The monthly series of one KPI over the last ``months`` months; an unknown ``variant`` is a 422."""
    area = areas.get_by_slug(area_slug)
    kpi = trends.get_kpi(kpi_key)
    chosen = kpi.variant(variant)
    result = trends.series(kpi, area, months, chosen)
    payload = {
        **_kpi_payload(kpi),
        "status": result.status,
        "message": result.message,
        "target": result.target,
        "periods": trends.month_periods(months),
        "points": [_point_payload(pt) for pt in result.points],
        "variant": chosen.key if chosen else None,
    }
    if chosen:
        payload["unit"] = chosen.unit or kpi.unit
        payload["description"] = chosen.description or kpi.description
        payload["variant_label"] = chosen.label
    return payload
