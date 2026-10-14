"""The strategy layer over HTTP: corporate projects (``/api/areas``), their thématiques and their
ranked objectives, plus the flat list of every thématique (``/api/thematics``). Every signed-in
user reads the projects; a project says which teams work in it (``teams``, each with its badge) and what
the caller may do with it (``can_manage``, ``can_delete``, ``can_place_microproject``: creating or moving
a µprojet there, ``attachable_teams``: the teams the caller could attach, ``manageable_teams``: those
they may create a thématique for, ``placement_teams``: those a µprojet they create may belong to) so
the page computes nothing. The project and its objectives are written by an admin or a manager of one of its teams
(:func:`service.can_manage`); a team is attached by an admin or its manager
(``POST /api/areas/{area}/teams``).

A thématique belongs to one team (``team``), says which teams are invited into it (``invited_teams``,
read-only guests) and what the caller may do with it (``can_manage``, ``can_place_microproject``). The
thématiques a caller does not see (:func:`service.visible_thematic_ids`) are left out of every
listing and are a 404.

What the µprojets of a project are doing (their counts, the thématique's frise) is read from the
experiments plugin (``GET /api/experiment-stats``, ``GET /api/experiment-timeline``), and a µprojet
moves between projects by ``PATCH /api/microprojects/{microproject_slug}``: this plugin, listed
below both, knows nothing of them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...kernel.errors import InvalidInput

from ..accounts.deps import current_user
from ..accounts.service import User
from ..teams import service as teams
from . import service as areas
from .schemas import AreaCreate, AreaPatch, ObjectiveCreate, ObjectivePatch, TeamRef, ThematicCreate, ThematicPatch
from .service import ManagementArea, Objective, Thematic

router = APIRouter(prefix="/api", tags=["areas"])


def _area_ref(area: ManagementArea) -> dict:
    return {"slug": area.slug, "name": area.name}


class _Viewer:
    """What the caller may do with each project and thématique, and the teams' badges - read once
    per request."""

    def __init__(self, user: User) -> None:
        self.user = user
        self._teams = {team.id: team for team in teams.list_all()}
        self._managed = areas.managed_area_ids(user)
        self._roles = teams.roles_of(user.id)
        self._my_teams = set(self._roles)
        self._managed_teams = teams.managed_team_ids(user.id)
        self._area_teams = areas.team_ids_by_area()
        self._invited = areas.invited_team_ids_by_thematic()

    def can_manage(self, area: ManagementArea) -> bool:
        return self.user.is_admin or area.id in self._managed

    def can_place_microproject(self, area: ManagementArea) -> bool:
        return areas.can_place_microproject(self.user, area, my_team_ids=self._my_teams)

    def team_refs(self, team_ids) -> list[dict]:
        return [self._teams[team_id].ref() for team_id in team_ids if team_id in self._teams]

    def teams(self, area: ManagementArea) -> list[dict]:
        return self.team_refs(self._area_teams.get(area.id, []))

    def attachable_teams(self, area: ManagementArea) -> list[dict]:
        """The teams the caller could attach to the project: those they manage (all, for an admin)
        that do not work in it yet - none in the system area."""
        if area.is_system:
            return []
        attached = set(self._area_teams.get(area.id, []))
        mine = self._teams if self.user.is_admin else {i: t for i, t in self._teams.items() if i in self._managed_teams}
        return [team.ref() for team_id, team in mine.items() if team_id not in attached]

    def manageable_teams(self, area: ManagementArea) -> list[dict]:
        """The teams of the project the caller may create a thématique for: those they manage (every
        team of the project for an admin)."""
        attached = self._area_teams.get(area.id, [])
        return self.team_refs([i for i in attached if self.user.is_admin or i in self._managed_teams])

    def placement_teams(self, area: ManagementArea) -> list[dict]:
        """The teams of the project a µprojet the caller creates there may belong to: those they are a
        member of (every team of the project for an admin)."""
        attached = self._area_teams.get(area.id, [])
        return self.team_refs([i for i in attached if self.user.is_admin or i in self._my_teams])

    def team(self, team_id: int | None) -> dict | None:
        team = self._teams.get(team_id)
        return team.ref() if team else None

    def can_manage_thematic(self, area: ManagementArea, thematic: Thematic) -> bool:
        return areas.can_manage_thematic(self.user, area, thematic, managed_team_ids=self._managed_teams)

    def can_place_in_thematic(self, thematic: Thematic) -> bool:
        return areas.can_place_in_thematic(self.user, thematic, my_team_ids=self._my_teams)

    def invited_teams(self, thematic: Thematic) -> list[dict]:
        return self.team_refs(self._invited.get(thematic.id, []))

    def invitable_teams(self, thematic: Thematic) -> list[dict]:
        """The teams that could be invited into the thématique - every one but its owner and its guests."""
        taken = {thematic.team_id, *self._invited.get(thematic.id, [])}
        return [team.ref() for team_id, team in self._teams.items() if team_id not in taken]


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
        "teams": viewer.teams(area),
        "attachable_teams": viewer.attachable_teams(area),
        "manageable_teams": viewer.manageable_teams(area),
        "placement_teams": viewer.placement_teams(area),
        "can_manage": can_manage,
        "can_delete": can_manage and not area.is_system,
        "can_place_microproject": viewer.can_place_microproject(area),
    }


def _thematic_payload(thematic: Thematic, area: ManagementArea, viewer: _Viewer, *, detail: bool = False) -> dict:
    payload = {
        "id": thematic.id,
        "slug": thematic.slug,
        "name": thematic.name,
        "description": thematic.description,
        "position": thematic.position,
        "area": _area_ref(area),
        "team": viewer.team(thematic.team_id),
        "invited_teams": viewer.invited_teams(thematic),
        "can_manage": viewer.can_manage_thematic(area, thematic),
        "can_place_microproject": viewer.can_place_in_thematic(thematic) and viewer.can_place_microproject(area),
    }
    if detail:
        payload["invitable_teams"] = viewer.invitable_teams(thematic) if payload["can_manage"] else []
    return payload


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
    """The project page's own data: the project, the thématiques the caller sees and its objectives."""
    viewer = _Viewer(user)
    return {
        **_area_payload(area, viewer),
        "thematics": [_thematic_payload(t, area, viewer) for t in areas.list_thematics(area.id, visible_to=user)],
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
    """The managers of one of its teams, or an admin."""
    area = _managed(area_slug, user)
    return _area_detail(areas.update(area, **body.model_dump(exclude_unset=True)), user)


@router.delete("/areas/{area_slug}", status_code=204)
def delete_area(area_slug: str, user: User = Depends(current_user)) -> Response:
    """Its µprojets go back to the system area; the system area itself can't be deleted (409)."""
    areas.delete(_managed(area_slug, user))
    return _no_content()


@router.post("/areas/{area_slug}/teams", status_code=201)
def attach_team(area_slug: str, body: TeamRef, response: Response, user: User = Depends(current_user)) -> dict:
    """The team works in the project - an admin, or the manager of that team (403 otherwise)."""
    area = areas.get_by_slug(area_slug)
    team = areas.team_of(body.team)
    if team is None:
        raise InvalidInput("précisez l'équipe", code="unknown_team")
    areas.attach_team(user, area, team)
    _created(response, f"/api/areas/{area.slug}")
    return _area_detail(area, user)


@router.delete("/areas/{area_slug}/teams/{team_slug}")
def detach_team(area_slug: str, team_slug: str, user: User = Depends(current_user)) -> dict:
    """The team leaves the project - an admin, or its manager; 409 ``team_has_content`` while it
    still owns thématiques or µprojets there."""
    area = areas.get_by_slug(area_slug)
    areas.detach_team(user, area, teams.get_by_slug(team_slug))
    return _area_detail(area, user)


# --- thématiques ------------------------------------------------------------------------------


@router.get("/thematics")
def list_thematics(area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """The thématiques the caller sees (of one project with ``?area=``), project by project - e.g. to
    pick those a lot aims at."""
    if area:
        project = areas.get_by_slug(area)
        by_id, thematics = {project.id: project}, areas.list_thematics(project.id, visible_to=user)
    else:
        by_id, thematics = {project.id: project for project in areas.list_all()}, areas.list_thematics(visible_to=user)
    viewer = _Viewer(user)
    return [
        {"id": t.id, "slug": t.slug, "name": t.name, "area": _area_ref(by_id[t.management_area_id]), "team": viewer.team(t.team_id)}
        for t in thematics
    ]


@router.post("/areas/{area_slug}/thematics", status_code=201)
def create_thematic(area_slug: str, body: ThematicCreate, response: Response, user: User = Depends(current_user)) -> dict:
    """For one of the area's teams: ``team`` (slug), left out when only one fits - the manager's
    only attached team, the area's only team for an admin (422 ``team_required`` otherwise)."""
    area = areas.get_by_slug(area_slug)
    team = areas.thematic_owner(user, area, areas.team_of(body.team))
    thematic = areas.create_thematic(area, body.name, body.description, created_by=user.id, team_id=team.id if team else None)
    _created(response, f"/api/areas/{area.slug}/thematics/{thematic.slug}")
    return _thematic_payload(thematic, area, _Viewer(user), detail=True)


@router.get("/areas/{area_slug}/thematics/{thematic_slug}")
def get_thematic(area_slug: str, thematic_slug: str, user: User = Depends(current_user)) -> dict:
    """404 for a thématique the caller does not see."""
    area = areas.get_by_slug(area_slug)
    return _thematic_payload(areas.get_visible_thematic(user, area.id, thematic_slug), area, _Viewer(user), detail=True)


def _managed_thematic(area_slug: str, thematic_slug: str, user: User) -> tuple[ManagementArea, Thematic]:
    """The thématique of the path, which the caller must manage (404 if they do not see it, 403
    otherwise)."""
    area = areas.get_by_slug(area_slug)
    thematic = areas.get_visible_thematic(user, area.id, thematic_slug)
    areas.require_manage_thematic(user, area, thematic)
    return area, thematic


@router.patch("/areas/{area_slug}/thematics/{thematic_slug}")
def update_thematic(area_slug: str, thematic_slug: str, body: ThematicPatch, user: User = Depends(current_user)) -> dict:
    area, thematic = _managed_thematic(area_slug, thematic_slug, user)
    thematic = areas.update_thematic(thematic, **body.model_dump(exclude_unset=True))
    return _thematic_payload(thematic, area, _Viewer(user), detail=True)


@router.delete("/areas/{area_slug}/thematics/{thematic_slug}", status_code=204)
def delete_thematic(area_slug: str, thematic_slug: str, user: User = Depends(current_user)) -> Response:
    """Its µprojets stay in the project, without thématique."""
    _, thematic = _managed_thematic(area_slug, thematic_slug, user)
    areas.delete_thematic(thematic)
    return _no_content()


@router.post("/areas/{area_slug}/thematics/{thematic_slug}/teams", status_code=201)
def invite_team(area_slug: str, thematic_slug: str, body: TeamRef, response: Response, user: User = Depends(current_user)) -> dict:
    """Invite a whole team: it reads the thématique and its µprojets (409 ``owner_team`` for the
    team that owns it). Whoever manages the thématique."""
    area, thematic = _managed_thematic(area_slug, thematic_slug, user)
    team = areas.team_of(body.team)
    if team is None:
        raise InvalidInput("précisez l'équipe", code="unknown_team")
    areas.invite_team(thematic, team)
    _created(response, f"/api/areas/{area.slug}/thematics/{thematic.slug}")
    return _thematic_payload(thematic, area, _Viewer(user), detail=True)


@router.delete("/areas/{area_slug}/thematics/{thematic_slug}/teams/{team_slug}")
def uninvite_team(area_slug: str, thematic_slug: str, team_slug: str, user: User = Depends(current_user)) -> dict:
    area, thematic = _managed_thematic(area_slug, thematic_slug, user)
    areas.uninvite_team(thematic, teams.get_by_slug(team_slug))
    return _thematic_payload(thematic, area, _Viewer(user), detail=True)


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
