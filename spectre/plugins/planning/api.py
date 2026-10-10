"""Le planning d'une équipe over HTTP : ``GET /api/team-plannings/{team_slug}`` (et
``GET /api/team-plannings`` : celui de la première équipe que l'on manage). Lecture seule - un lot
prévu se crée et se remplit par les routes du plugin lots (``POST /api/lots``,
``POST /api/lots/{lot_id}/wafers``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as planning

router = APIRouter(prefix="/api", tags=["planning"])


@router.get("/team-plannings")
def default_planning(user: User = Depends(current_user)) -> dict:
    """Le planning de la première équipe que l'on manage (``team`` à ``null`` s'il n'y en a pas)."""
    return planning.board(user)


@router.get("/team-plannings/{team_slug}")
def team_planning(team_slug: str, user: User = Depends(current_user)) -> dict:
    """Le planning de l'équipe ``team_slug`` - 404 si elle n'existe pas, 403 hors de ses managers."""
    return planning.board(user, team_slug=team_slug)
