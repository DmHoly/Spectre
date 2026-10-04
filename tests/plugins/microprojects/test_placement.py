"""Placer un µprojet dans un projet - le créer (``POST /api/microprojects``) ou l'y déplacer
(``PATCH /api/microprojects/{mp}`` ``{area}``) : dans le projet d'une équipe, ses membres (tout rôle)
et un administrateur seulement (403 ``placement_forbidden``) ; un projet sans équipe et « Non
classé » restent ouverts à tous. Chaque projet le dit à l'appelant : ``can_place_microproject``."""

from __future__ import annotations

import pytest

from support.accounts import login, signup
from support.http import assert_created, assert_ok
from support.microprojects import create_microproject, get_microproject, move_microproject
from support.teams import add_team_member, team_world

# peut-il placer un µprojet dans « theme-a », le projet de l'équipe A ?
TEAM_AREA = {
    "admin": True,
    "manager_a": True,  # gère le projet
    "member_a": True,  # simple membre de l'équipe
    "manager_b": False,  # manager d'une autre équipe
    "member_b": False,  # simple membre d'une autre équipe
    "researcher": False,  # dans aucune équipe
}
OPEN_AREAS = ("native-pt2", "non-classe")  # sans équipe, et « Non classé »


def _world(client):
    """Le monde des droits d'équipe, plus ``member_b``, simple membre de l'équipe B - renvoie
    ``(world, {qui: e-mail})``."""
    world = team_world(client)
    signup(client, "equipier-b@example.com", name="equipier-b")
    login(client, world.admin)
    assert_created(add_team_member(client, "equipe-b", "equipier-b@example.com", "member"))
    accounts = {who: getattr(world, who) for who in TEAM_AREA if who != "member_b"}
    return world, {**accounts, "member_b": "equipier-b@example.com"}


def _refused(response) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "placement_forbidden"
    assert "Thème A" in body["detail"] and "équipe" in body["detail"]


@pytest.mark.parametrize("who", sorted(TEAM_AREA))
def test_each_project_says_whether_the_caller_may_place_a_microproject_in_it(client, who):
    _, accounts = _world(client)
    login(client, accounts[who])
    placeable = {area["slug"]: area["can_place_microproject"] for area in assert_ok(client.get("/api/areas"))}
    assert placeable.pop("theme-a") is TEAM_AREA[who]
    assert set(OPEN_AREAS) <= set(placeable) and all(placeable.values())  # les projets sans équipe, « Non classé » compris
    assert assert_ok(client.get("/api/areas/theme-a"))["can_place_microproject"] is TEAM_AREA[who]
    assert assert_ok(client.get("/api/areas?team=equipe-a"))[0]["can_place_microproject"] is TEAM_AREA[who]


@pytest.mark.parametrize("who", sorted(TEAM_AREA))
def test_creating_a_microproject_in_a_team_project(client, who):
    _, accounts = _world(client)
    login(client, accounts[who])
    response = client.post("/api/microprojects", json={"name": "Gravure", "area": "theme-a", "thematic": "t"})
    if TEAM_AREA[who]:
        created = assert_created(response)
        assert (created["area"]["slug"], created["thematic"]["slug"]) == ("theme-a", "t")
    else:
        _refused(response)
        login(client, accounts["admin"])
        assert [p["slug"] for p in assert_ok(client.get("/api/microprojects", params={"scope": "all"})) if p["name"] == "Gravure"] == []


@pytest.mark.parametrize("who", sorted(TEAM_AREA))
@pytest.mark.parametrize("area", OPEN_AREAS)
def test_creating_a_microproject_in_a_project_without_team_is_open_to_all(client, who, area):
    _, accounts = _world(client)
    login(client, accounts[who])
    assert create_microproject(client, "Gravure", area=area)["area"]["slug"] == area


def test_creating_without_project_lands_in_unclassified_for_anyone(client):
    _, accounts = _world(client)
    login(client, accounts["researcher"])
    assert create_microproject(client, "Gravure")["area"]["slug"] == "non-classe"


@pytest.mark.parametrize("who", sorted(TEAM_AREA))
def test_moving_a_microproject_into_a_team_project(client, who):
    """Chacun déplace son propre µprojet (le rôle owner, inchangé) ; vers le projet d'une équipe, il
    faut en plus en être membre ou administrateur."""
    _, accounts = _world(client)
    login(client, accounts[who])
    slug = create_microproject(client, "Gravure")["slug"]
    response = client.patch(f"/api/microprojects/{slug}", json={"area": "theme-a", "thematic": "t"})
    if TEAM_AREA[who]:
        moved = assert_ok(response)
        assert (moved["area"]["slug"], moved["thematic"]["slug"]) == ("theme-a", "t")
        assert moved["code"]  # numéroté en arrivant dans un projet qui numérote
    else:
        _refused(response)
        unchanged = get_microproject(client, slug)
        assert (unchanged["area"]["slug"], unchanged["thematic"], unchanged["code"]) == ("non-classe", None, None)


@pytest.mark.parametrize("who", sorted(TEAM_AREA))
def test_moving_a_microproject_to_a_project_without_team_is_open_to_all(client, who):
    _, accounts = _world(client)
    login(client, accounts[who])
    slug = create_microproject(client, "Gravure")["slug"]
    assert move_microproject(client, "native-pt2", slug)["area"]["slug"] == "native-pt2"
    assert move_microproject(client, "non-classe", slug)["area"]["slug"] == "non-classe"


def test_an_owner_outside_the_team_keeps_his_microproject_already_in_the_team_project(client):
    """« recuit » est dans le Thème A, son propriétaire n'est pas de l'équipe : il le modifie, le
    change de thématique dans ce projet (pas de nouveau placement), et l'en sort - sans pouvoir l'y
    remettre."""
    world, _ = _world(client)
    login(client, world.researcher)
    assert assert_ok(client.patch("/api/microprojects/recuit", json={"name": "Recuit rapide", "area": "theme-a"}))["name"] == "Recuit rapide"
    assert move_microproject(client, "theme-a", "recuit", "t")["thematic"]["slug"] == "t"
    assert move_microproject(client, "native-pt2", "recuit")["area"]["slug"] == "native-pt2"
    _refused(client.patch("/api/microprojects/recuit", json={"area": "theme-a"}))


def test_the_rule_follows_the_team_membership(client):
    """Retiré de l'équipe, on n'y place plus de µprojet ; ajouté à une équipe, on y place les siens."""
    world, _ = _world(client)
    login(client, world.admin)
    assert client.delete(f"/api/teams/equipe-a/members/{world.ids[world.member_a]}").status_code == 204
    assert_created(add_team_member(client, "equipe-a", world.researcher, "member"))
    login(client, world.member_a)
    _refused(client.post("/api/microprojects", json={"name": "Gravure", "area": "theme-a"}))
    login(client, world.researcher)
    assert move_microproject(client, "theme-a", "orphelin")["area"]["slug"] == "theme-a"
