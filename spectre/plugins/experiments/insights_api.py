"""The transverse readings of the experiments over HTTP (see :mod:`spectre.plugins.experiments.insights`):
collections under ``/api``, filtered by query params, for any signed-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from ..accounts.service import User
from . import insights

router = APIRouter(prefix="/api", tags=["experiments"])


@router.get("/experiment-stats")
def experiment_stats(microproject: str | None = None, area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """``[{microproject, running, concluded, abandoned, wafers}]`` - every µprojet, or those of one
    project (``?area=``), or one µprojet (``?microproject=``)."""
    return insights.stats(user, microproject_slug=microproject, area_slug=area)


@router.get("/experiment-timeline")
def experiment_timeline(area: str, thematic: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """``[{microproject, nodes}]`` - the frise of a project's µprojets (of one thématique with
    ``?thematic=``), redacted for non-members."""
    return insights.timeline(user, area_slug=area, thematic_slug=thematic)
