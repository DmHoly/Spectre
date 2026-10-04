"""Les droits sur un projet corporate, ses thématiques et ses objectifs (``areas.service.can_manage``) :
un administrateur, ou un manager de l'équipe du projet. Un manager d'une autre équipe, un simple
membre d'équipe, un membre d'un µprojet ou un inconnu lisent seulement."""

from __future__ import annotations

import pytest

from support.accounts import login
from support.areas import get_area
from support.http import assert_ok
from support.teams import set_team_member_role, team_world

READERS = ("manager_b", "member_a", "researcher", "viewer", "stranger")
WRITERS = ("admin", "manager_a")


def _writes(client, objective_id: int) -> dict[str, int]:
    """Chaque route d'écriture du thème A, dans un ordre qui la laisse rejouable : le statut reçu."""
    calls = {
        "patch area": lambda: client.patch("/api/areas/theme-a", json={"description": "Revue"}),
        "create thematic": lambda: client.post("/api/areas/theme-a/thematics", json={"name": "Nouvelle"}),
        "patch thematic": lambda: client.patch("/api/areas/theme-a/thematics/t", json={"description": "d"}),
        "delete thematic": lambda: client.delete("/api/areas/theme-a/thematics/nouvelle"),
        "create objective": lambda: client.post("/api/areas/theme-a/objectives", json={"title": "Autre"}),
        "patch objective": lambda: client.patch(f"/api/areas/theme-a/objectives/{objective_id}", json={"target": "T2"}),
    }
    return {name: call().status_code for name, call in calls.items()}


@pytest.mark.parametrize("who", WRITERS)
def test_the_admin_and_the_team_manager_write_the_area(client, who):
    world = team_world(client)
    login(client, getattr(world, who))
    area = get_area(client, "theme-a")
    assert (area["can_manage"], area["can_delete"]) == (True, True)
    assert area["team"] == {"slug": "equipe-a", "name": "Équipe A"}
    assert _writes(client, world.objective_id) == {
        "patch area": 200,
        "create thematic": 201,
        "patch thematic": 200,
        "delete thematic": 204,
        "create objective": 201,
        "patch objective": 200,
    }
    deleted = client.delete(f"/api/areas/theme-a/objectives/{world.objective_id}")
    assert deleted.status_code == 204
    assert client.delete("/api/areas/theme-a").status_code == 204


@pytest.mark.parametrize("who", READERS)
def test_anyone_else_only_reads_the_area(client, who):
    world = team_world(client)
    login(client, getattr(world, who))
    area = get_area(client, "theme-a")
    assert (area["can_manage"], area["can_delete"]) == (False, False)
    assert set(_writes(client, world.objective_id).values()) == {403}
    assert client.delete(f"/api/areas/theme-a/objectives/{world.objective_id}").status_code == 403
    assert client.delete("/api/areas/theme-a").status_code == 403


def test_a_manager_only_manages_the_areas_of_their_team(client):
    world = team_world(client)
    login(client, world.manager_a)
    flags = {a["slug"]: a["can_manage"] for a in assert_ok(client.get("/api/areas"))}
    assert flags == {"theme-a": True, "native-pt2": False, "datacom-vlc": False, "nova-pt1": False, "non-classe": False}
    # un thème sans équipe et le thème système restent à l'administrateur
    assert client.patch("/api/areas/native-pt2", json={"description": "x"}).status_code == 403
    assert client.post("/api/areas/native-pt2/thematics", json={"name": "x"}).status_code == 403
    assert client.patch("/api/areas/non-classe", json={"description": "x"}).status_code == 403

    # rétrogradé simple membre de son équipe, il perd ces droits
    login(client, world.admin)
    assert set_team_member_role(client, "equipe-a", world.ids[world.member_a], "manager").status_code == 200  # l'équipe garde un manager
    assert set_team_member_role(client, "equipe-a", world.ids[world.manager_a], "member").status_code == 200
    login(client, world.manager_a)
    assert client.patch("/api/areas/theme-a", json={"description": "x"}).status_code == 403


def test_a_manager_creates_an_area_only_in_one_of_their_teams(client):
    world = team_world(client)
    login(client, world.manager_a)
    assert client.post("/api/areas", json={"name": "Sans équipe"}).status_code == 403
    assert client.post("/api/areas", json={"name": "Chez B", "team": "equipe-b"}).status_code == 403
    unknown = client.post("/api/areas", json={"name": "X", "team": "inconnue"})
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_team"
    created = client.post("/api/areas", json={"name": "Chez A", "team": "equipe-a"})
    assert created.status_code == 201 and created.headers["location"] == "/api/areas/chez-a"
    assert (created.json()["team"]["slug"], created.json()["can_manage"]) == ("equipe-a", True)

    login(client, world.member_a)  # membre, pas manager, de l'équipe A
    assert client.post("/api/areas", json={"name": "Non", "team": "equipe-a"}).status_code == 403
    login(client, world.stranger)
    assert client.post("/api/areas", json={"name": "Non"}).status_code == 403

    login(client, world.admin)  # l'administrateur, avec ou sans équipe
    assert client.post("/api/areas", json={"name": "Libre"}).json()["team"] is None
    assert client.post("/api/areas", json={"name": "Chez B", "team": "equipe-b"}).json()["team"]["slug"] == "equipe-b"


def test_attaching_an_area_to_a_team_is_the_admins_alone(client):
    world = team_world(client)
    login(client, world.manager_a)
    for team in ("equipe-b", None, "equipe-a"):
        assert client.patch("/api/areas/theme-a", json={"team": team}).status_code == 403
    assert get_area(client, "theme-a")["team"]["slug"] == "equipe-a"  # rien n'a changé

    login(client, world.admin)
    moved = client.patch("/api/areas/theme-a", json={"team": "equipe-b", "description": "Passé à B"})
    assert moved.status_code == 200
    assert (moved.json()["team"]["slug"], moved.json()["description"]) == ("equipe-b", "Passé à B")
    assert client.patch("/api/areas/theme-a", json={"team": "inconnue"}).status_code == 422
    login(client, world.manager_a)
    assert client.patch("/api/areas/theme-a", json={"description": "x"}).status_code == 403
    login(client, world.manager_b)
    assert client.patch("/api/areas/theme-a", json={"description": "x"}).status_code == 200

    login(client, world.admin)
    assert client.patch("/api/areas/theme-a", json={"team": None}).json()["team"] is None
    # le thème système reste sans équipe
    refused = client.patch("/api/areas/non-classe", json={"team": "equipe-a"})
    assert refused.status_code == 409
    assert client.patch("/api/areas/non-classe", json={"team": None}).status_code == 200  # sans effet


def test_areas_are_listed_by_team(client):
    team_world(client)
    assert [a["slug"] for a in assert_ok(client.get("/api/areas", params={"team": "equipe-a"}))] == ["theme-a"]
    assert assert_ok(client.get("/api/areas", params={"team": "equipe-b"})) == []
    assert client.get("/api/areas", params={"team": "inconnue"}).status_code == 404
