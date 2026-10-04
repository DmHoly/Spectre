"""The strategy layer over HTTP: corporate projects (``/api/areas``), their thématiques and their
ranked objectives, plus the flat list of every thématique (``/api/thematics``). Every signed-in
user reads them; every write goes through one rule, :func:`service.can_manage` (an admin, or a
manager of the project's team), and each project says what the caller may do with it
(``can_manage``, ``can_delete``, and ``can_place_microproject``: creating or moving a µprojet
there, :func:`service.can_place_microproject`) so the page computes nothing. Attaching a project to a team
(``PATCH {team}``) is the admin's alone.

What the µprojets of a project are doing (their counts, the thématique's frise) is read from the
experiments plugin (``GET /api/experiment-stats``, ``GET /api/experiment-timeline``), and a µprojet
moves between projects by ``PATCH /api/microprojects/{microproject_slug}``: this plugin, listed
below both, knows nothing of them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..accounts.deps import current_user
from ..accounts.service import User
from ..teams import service as teams
from . import service as areas
from .schemas import AreaCreate, AreaPatch, ObjectiveCreate, ObjectivePatch, ThematicCreate, ThematicPatch
from .service import ManagementArea, Objective, Thematic

router = APIRouter(prefix="/api", tags=["areas"])


def _area_ref(area: ManagementArea) -> dict:
    return {"slug": area.slug, "name": area.name}


class _Viewer:
    """What the caller may do with each project, and the teams' names - read once per request."""

    def __init__(self, user: User) -> None:
        self.user = user
        self._teams = {team.id: team for team in teams.list_all()}
        self._managed = areas.managed_area_ids(user)
        self._my_teams = set(teams.roles_of(user.id))

    def can_manage(self, area: ManagementArea) -> bool:
        return self.user.is_admin or area.id in self._managed

    def can_place_microproject(self, area: ManagementArea) -> bool:
        return areas.can_place_microproject(self.user, area, my_team_ids=self._my_teams)

    def team(self, area: ManagementArea) -> dict | None:
        team = self._teams.get(area.team_id)
        return {"slug": team.slug, "name": team.name} if team else None


def _area_payload(area: ManagementArea, viewer: _Viewer) -> dict:
    can_manage = viewer.can_manage(area)
    return {
        "id": area.id,
        "slug": area.slug,
        "name": area.name,
        "description": area.description,
        "strategy": area.strategy,
        "objectives_period": area.objectives_period,
        "horizon_months": area.horizon_months,
        "code_prefix": area.code_prefix,
        "is_system": area.is_system,
        "team": viewer.team(area),
        "can_manage": can_manage,
        "can_delete": can_manage and not area.is_system,
        "can_place_microproject": viewer.can_place_microproject(area),
    }


def _thematic_payload(thematic: Thematic, area: ManagementArea) -> dict:
    return {
        "id": thematic.id,
        "slug": thematic.slug,
        "name": thematic.name,
        "description": thematic.description,
        "position": thematic.position,
        "area": _area_ref(area),
    }


def _objective_payload(objective: Objective) -> dict:
    return {
        "id": objective.id,
        "title": objective.title,
        "detail": objective.detail,
        "target": objective.target,
        "weight": objective.weight,
        "achieved": objective.achieved,
        "validated_by": objective.validated_by,
        "position": objective.position,
    }


def _area_detail(area: ManagementArea, user: User) -> dict:
    """The project page's own data: the project, its thématiques and its objectives."""
    return {
        **_area_payload(area, _Viewer(user)),
        "thematics": [_thematic_payload(t, area) for t in areas.list_thematics(area.id)],
        "objectives": [_objective_payload(o) for o in areas.list_objectives(area.id)],
    }


def _created(response: Response, location: str) -> None:
    response.headers["Location"] = location


def _no_content() -> Response:
    return Response(status_code=204)


def _managed(area_slug: str, user: User) -> ManagementArea:
    """The project of the path, which the caller must manage (403 otherwise)."""
    area = areas.get_by_slug(area_slug)
    areas.require_manage(user, area)
    return area


# --- projets corporate -------------------------------------------------------------------------


@router.get("/areas")
def list_areas(team: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """Every project (of one team with ``?team=``, unknown: 404), the system one (« Non classé »)
    last."""
    team_id = teams.get_by_slug(team).id if team else None
    viewer = _Viewer(user)
    return [_area_payload(area, viewer) for area in areas.list_all(team_id=team_id)]


@router.post("/areas", status_code=201)
def create_area(body: AreaCreate, response: Response, user: User = Depends(current_user)) -> dict:
    """An admin, or a manager attaching it to one of their teams (``team``)."""
    team = areas.team_of(body.team)
    areas.check_can_create(user, team)
    area = areas.create(
        body.name, body.description, body.strategy, created_by=user.id, code_prefix=body.code_prefix, team_id=team.id if team else None
    )
    _created(response, f"/api/areas/{area.slug}")
    return _area_detail(area, user)


@router.get("/areas/{area_slug}")
def get_area(area_slug: str, user: User = Depends(current_user)) -> dict:
    return _area_detail(areas.get_by_slug(area_slug), user)


@router.patch("/areas/{area_slug}")
def update_area(area_slug: str, body: AreaPatch, user: User = Depends(current_user)) -> dict:
    """Its team's managers or an admin; ``team`` (the team that owns it, ``null``: none) an admin only."""
    area = _managed(area_slug, user)
    changes = body.model_dump(exclude_unset=True)
    if "team" in changes:
        area = areas.set_team(user, area, areas.team_of(changes.pop("team")))
    return _area_detail(areas.update(area, **changes), user)


@router.delete("/areas/{area_slug}", status_code=204)
def delete_area(area_slug: str, user: User = Depends(current_user)) -> Response:
    """Its µprojets go back to the system area; the system area itself can't be deleted (409)."""
    areas.delete(_managed(area_slug, user))
    return _no_content()


# --- thématiques ------------------------------------------------------------------------------


@router.get("/thematics")
def list_thematics(area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """Every thématique (of one project with ``?area=``), project by project - e.g. to pick those a
    lot aims at."""
    if area:
        project = areas.get_by_slug(area)
        by_id, thematics = {project.id: project}, areas.list_thematics(project.id)
    else:
        by_id, thematics = {project.id: project for project in areas.list_all()}, areas.list_thematics()
    return [{"id": t.id, "slug": t.slug, "name": t.name, "area": _area_ref(by_id[t.management_area_id])} for t in thematics]


@router.post("/areas/{area_slug}/thematics", status_code=201)
def create_thematic(area_slug: str, body: ThematicCreate, response: Response, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    thematic = areas.create_thematic(area, body.name, body.description, created_by=user.id)
    _created(response, f"/api/areas/{area.slug}/thematics/{thematic.slug}")
    return _thematic_payload(thematic, area)


@router.get("/areas/{area_slug}/thematics/{thematic_slug}")
def get_thematic(area_slug: str, thematic_slug: str, user: User = Depends(current_user)) -> dict:
    area = areas.get_by_slug(area_slug)
    return _thematic_payload(areas.get_thematic(area.id, thematic_slug), area)


@router.patch("/areas/{area_slug}/thematics/{thematic_slug}")
def update_thematic(area_slug: str, thematic_slug: str, body: ThematicPatch, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    thematic = areas.update_thematic(areas.get_thematic(area.id, thematic_slug), **body.model_dump(exclude_unset=True))
    return _thematic_payload(thematic, area)


@router.delete("/areas/{area_slug}/thematics/{thematic_slug}", status_code=204)
def delete_thematic(area_slug: str, thematic_slug: str, user: User = Depends(current_user)) -> Response:
    """Its µprojets stay in the project, without thématique."""
    area = _managed(area_slug, user)
    areas.delete_thematic(areas.get_thematic(area.id, thematic_slug))
    return _no_content()


# --- objectifs corporate ----------------------------------------------------------------------


@router.post("/areas/{area_slug}/objectives", status_code=201)
def create_objective(area_slug: str, body: ObjectiveCreate, response: Response, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    objective = areas.create_objective(
        area,
        body.title,
        body.detail,
        body.target,
        weight=body.weight,
        achieved=body.achieved,
        validated_by=body.validated_by,
        created_by=user.id,
    )
    _created(response, f"/api/areas/{area.slug}/objectives/{objective.id}")
    return _objective_payload(objective)


@router.get("/areas/{area_slug}/objectives/{objective_id}")
def get_objective(area_slug: str, objective_id: int, user: User = Depends(current_user)) -> dict:
    return _objective_payload(areas.get_objective(areas.get_by_slug(area_slug), objective_id))


@router.patch("/areas/{area_slug}/objectives/{objective_id}")
def update_objective(area_slug: str, objective_id: int, body: ObjectivePatch, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    return _objective_payload(areas.update_objective(area, objective_id, **body.model_dump(exclude_unset=True)))


@router.delete("/areas/{area_slug}/objectives/{objective_id}", status_code=204)
def delete_objective(area_slug: str, objective_id: int, user: User = Depends(current_user)) -> Response:
    areas.delete_objective(_managed(area_slug, user), objective_id)
    return _no_content()
