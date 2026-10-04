"""Teams over HTTP: ``/api/teams`` and ``/api/teams/{team_slug}/members``. Every signed-in user
reads them (who manages what is a company-wide fact, like the corporate projects); an admin
creates, renames and deletes a team (:func:`spectre.plugins.accounts.deps.require_admin`); an admin
or a manager of the team manages its members (:func:`service.require_manage`).

Each team says what the caller may do with it - ``my_role`` (``manager``, ``member`` or ``null``),
``can_edit`` (rename, delete: an admin) and ``can_manage`` (its members) - so the page computes
nothing. The corporate projects a team owns are read from the areas plugin
(``GET /api/areas?team=``): this plugin, listed below it, knows nothing of them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...kernel.http import created
from ..accounts.deps import current_user, require_admin
from ..accounts.service import User
from . import service as teams
from .schemas import TeamCreate, TeamMemberCreate, TeamMemberPatch, TeamPatch
from .service import Team

router = APIRouter(prefix="/api", tags=["teams"])


def _url(team: Team) -> str:
    return f"/api/teams/{team.slug}"


def _payloads(found: list[Team], user: User) -> list[dict]:
    summaries = teams.summaries([team.id for team in found])
    roles = teams.roles_of(user.id)
    return [
        {
            "id": team.id,
            "slug": team.slug,
            "name": team.name,
            "created_at": team.created_at,
            **summaries[team.id],
            "my_role": roles.get(team.id),
            "can_edit": user.is_admin,
            "can_manage": user.is_admin or roles.get(team.id) == "manager",
        }
        for team in found
    ]


def _payload(team: Team, user: User) -> dict:
    return _payloads([team], user)[0]


def _managed(team_slug: str, user: User) -> Team:
    team = teams.get_by_slug(team_slug)
    teams.require_manage(user, team)
    return team


# -- équipes ----------------------------------------------------------------------------------------


@router.get("/teams")
def list_teams(user: User = Depends(current_user)) -> list[dict]:
    """Every team, by name."""
    return _payloads(teams.list_all(), user)


@router.post("/teams", status_code=201)
def create_team(body: TeamCreate, response: Response, user: User = Depends(require_admin)) -> dict:
    team = teams.create(body.name)
    created(response, _url(team))
    return _payload(team, user)


@router.get("/teams/{team_slug}")
def get_team(team_slug: str, user: User = Depends(current_user)) -> dict:
    return _payload(teams.get_by_slug(team_slug), user)


@router.patch("/teams/{team_slug}")
def update_team(team_slug: str, body: TeamPatch, user: User = Depends(require_admin)) -> dict:
    team = teams.get_by_slug(team_slug)
    if body.name is not None:
        team = teams.rename(team, body.name)
    return _payload(team, user)


@router.delete("/teams/{team_slug}", status_code=204)
def delete_team(team_slug: str, user: User = Depends(require_admin)) -> Response:
    """Its members go with it; its corporate projects stay, without a team."""
    teams.delete(teams.get_by_slug(team_slug))
    return Response(status_code=204)


# -- membres ----------------------------------------------------------------------------------------


@router.get("/teams/{team_slug}/members")
def list_members(team_slug: str, user: User = Depends(current_user)) -> list[dict]:
    """``[{id, name, email, role}]``, the managers first."""
    return teams.list_members(teams.get_by_slug(team_slug).id)


@router.post("/teams/{team_slug}/members", status_code=201)
def add_member(team_slug: str, body: TeamMemberCreate, response: Response, user: User = Depends(current_user)) -> dict:
    """An existing account, by its e-mail (404 ``no_account`` otherwise, 409 ``already_member``)."""
    team = _managed(team_slug, user)
    member = teams.add_member(team, body.email, body.role)
    created(response, f"{_url(team)}/members/{member['id']}")
    return member


@router.get("/teams/{team_slug}/members/{user_id}")
def get_member(team_slug: str, user_id: int, user: User = Depends(current_user)) -> dict:
    """One member - 404 if this account is not in the team."""
    return teams.get_member(teams.get_by_slug(team_slug).id, user_id)


@router.patch("/teams/{team_slug}/members/{user_id}")
def change_member_role(team_slug: str, user_id: int, body: TeamMemberPatch, user: User = Depends(current_user)) -> dict:
    """409 ``last_manager`` if that would leave the team without a manager."""
    return teams.change_member_role(_managed(team_slug, user), user_id, body.role)


@router.delete("/teams/{team_slug}/members/{user_id}", status_code=204)
def remove_member(team_slug: str, user_id: int, user: User = Depends(current_user)) -> Response:
    """409 ``last_manager`` for the last manager of the team."""
    teams.remove_member(_managed(team_slug, user), user_id)
    return Response(status_code=204)
