"""La fiche d'une étude fictive derrière un point d'une tendance de démonstration (voir
:mod:`spectre.plugins.kpis_demo.service`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from .service import demo_study

router = APIRouter(prefix="/api/areas", tags=["kpis-demo"])


@router.get("/{area_slug}/kpis/{kpi_key}/studies/{study_id}")
def get_study(area_slug: str, kpi_key: str, study_id: str, user: User = Depends(current_user)) -> dict:
    """The fiche of the study behind a point of a demo trend - a mock: structure, objective,
    conclusion and a symbolic view of its experiment tree."""
    return demo_study(areas.get_by_slug(area_slug), kpi_key, study_id)
