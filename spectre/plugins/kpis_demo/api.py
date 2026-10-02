"""La fiche d'une étude fictive derrière un point d'une tendance de démonstration (voir
:mod:`spectre.plugins.kpis_demo.service`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as management
from ..areas.service import ManagementArea, ManagementAreaNotFoundError
from ..kpis import service as trends
from .service import demo_study

router = APIRouter(prefix="/api/management", tags=["kpis-demo"])


def _get_area(slug: str) -> ManagementArea:
    try:
        return management.get_by_slug(slug)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def _get_kpi(kpi_key: str) -> trends.KpiDefinition:
    try:
        return trends.get_kpi(kpi_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"KPI {kpi_key!r} inconnu") from exc


@router.get("/{slug}/tendances/{kpi_key}/etudes/{study_id}")
def get_trend_study(slug: str, kpi_key: str, study_id: str, user: User = Depends(current_user)) -> dict:
    """The fiche of the study behind a point of a demo trend (see :mod:`spectre.plugins.kpis_demo.service`)
    - a mock: structure, objective, conclusion and a symbolic view of its experiment tree."""
    area = _get_area(slug)
    kpi = _get_kpi(kpi_key)
    if not kpi.demo:
        raise HTTPException(status_code=404, detail="pas de fiche d'étude pour ce KPI")
    try:
        return demo_study(area, study_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"étude {study_id!r} introuvable") from exc
