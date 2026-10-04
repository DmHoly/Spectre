"""Équipes et leurs membres (plugin teams) : un helper par route, et le monde de test des droits
d'équipe (:func:`team_world`)."""

from __future__ import annotations

from typing import Any, NamedTuple

from .accounts import login, signup
from .areas import create_area, create_objective, create_thematic, set_area_team
from .http import assert_created, assert_ok
from .microprojects import add_member as add_microproject_member
from .microprojects import create_microproject, move_microproject


def _url(team_slug: str) -> str:
    return f"/api/teams/{team_slug}"


def create_team(client: Any, name: str) -> dict:
    """POST /api/teams (admin) - renvoie l'équipe."""
    return assert_created(client.post("/api/teams", json={"name": name}))


def list_teams(client: Any) -> list[dict]:
    return assert_ok(client.get("/api/teams"))


def get_team(client: Any, team_slug: str) -> dict:
    return assert_ok(client.get(_url(team_slug)))


def team_members(client: Any, team_slug: str) -> list[dict]:
    return assert_ok(client.get(f"{_url(team_slug)}/members"))


def add_team_member(client: Any, team_slug: str, email: str, role: str = "member") -> Any:
    """POST .../members {email, role} - renvoie la réponse."""
    return client.post(f"{_url(team_slug)}/members", json={"email": email, "role": role})


def set_team_member_role(client: Any, team_slug: str, user_id: int, role: str) -> Any:
    """PATCH .../members/{user_id} - renvoie la réponse."""
    return client.patch(f"{_url(team_slug)}/members/{user_id}", json={"role": role})


def remove_team_member(client: Any, team_slug: str, user_id: int) -> Any:
    """DELETE .../members/{user_id} - renvoie la réponse."""
    return client.delete(f"{_url(team_slug)}/members/{user_id}")


class TeamWorld(NamedTuple):
    """Les comptes (par e-mail) et ce qu'ils possèdent, pour les tests de droits."""

    admin: str  # le premier compte : administrateur
    manager_a: str  # manager de l'équipe A, propriétaire du thème « Thème A »
    manager_b: str  # manager de l'équipe B
    member_a: str  # simple membre de l'équipe A
    researcher: str  # a créé les µprojets (owner par adhésion), dans aucune équipe
    viewer: str  # viewer du µprojet « recuit » par adhésion
    stranger: str  # rien de tout cela
    ids: dict[str, int]  # e-mail -> id du compte
    objective_id: int  # un objectif du « Thème A »


def team_world(client: Any) -> TeamWorld:
    """Deux équipes, un thème rattaché à l'équipe A (« theme-a », avec la thématique « t » et un
    objectif), et trois µprojets créés par ``researcher`` : « recuit » dans le Thème A (``viewer``
    y est lecteur ; hors de l'équipe A, ``researcher`` le crée dans « Non classé » et l'admin l'y
    range), « orphelin » dans « Non classé », « ailleurs » dans un thème sans équipe (native-pt2).
    Le client reste connecté en administrateur."""
    emails = ("boss@example.com", "chef-a@example.com", "chef-b@example.com", "equipier-a@example.com",
              "chercheur@example.com", "lecteur@example.com", "inconnu@example.com")
    ids = {email: signup(client, email, name=email.split("@")[0])["id"] for email in emails}
    admin, manager_a, manager_b, member_a, researcher, viewer, stranger = emails

    login(client, admin)
    create_team(client, "Équipe A")
    create_team(client, "Équipe B")
    assert_created(add_team_member(client, "equipe-a", manager_a, "manager"))
    assert_created(add_team_member(client, "equipe-a", member_a, "member"))
    assert_created(add_team_member(client, "equipe-b", manager_b, "manager"))
    create_area(client, "Thème A")
    set_area_team(client, "theme-a", "equipe-a")
    create_thematic(client, "theme-a", "T")
    objective = create_objective(client, "theme-a", "O")

    login(client, researcher)
    create_microproject(client, "Recuit")
    create_microproject(client, "Orphelin")
    create_microproject(client, "Ailleurs", area="native-pt2")
    add_microproject_member(client, "recuit", viewer, "viewer")

    login(client, admin)
    move_microproject(client, "theme-a", "recuit")
    return TeamWorld(admin, manager_a, manager_b, member_a, researcher, viewer, stranger, ids, objective["id"])
