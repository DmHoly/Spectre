"""Les droits sur un projet corporate, ses thématiques et ses objectifs (``areas.service.can_manage``) :
un administrateur, ou un manager d'une équipe qui y travaille. Un manager d'une autre équipe, un
simple membre d'équipe, un membre d'un µprojet ou un inconnu lisent seulement - et une thématique
d'une autre équipe ne se voit même pas (404)."""

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
    assert [team["slug"] for team in area["teams"]] == ["equipe-a"]
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
    writes = _writes(client, world.objective_id)
    # la thématique « t » est celle de l'équipe A : ses membres la voient (403), les autres non (404)
    visible = who == "member_a"
    assert writes.pop("patch thematic") == (403 if visible else 404)
    assert writes.pop("delete thematic") == 404  # « nouvelle » n'existe pas : rien n'a été créé
    assert set(writes.values()) == {403}
    assert client.delete(f"/api/areas/theme-a/objectives/{world.objective_id}").status_code == 403
    assert client.delete("/api/areas/theme-a").status_code == 403


def test_a_manager_only_manages_the_areas_of_their_teams(client):
    world = team_world(client)
    login(client, world.manager_a)
    flags = {a["slug"]: a["can_manage"] for a in assert_ok(client.get("/api/areas"))}
    assert flags == {"theme-a": True, "native-pt2": False, "datacom-vlc": False, "nova-pt1": False, "non-classe": False}
    # un thème où son équipe ne travaille pas et le thème système restent à l'administrateur
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
    assert ([t["slug"] for t in created.json()["teams"]], created.json()["can_manage"]) == (["equipe-a"], True)

    login(client, world.member_a)  # membre, pas manager, de l'équipe A
    assert client.post("/api/areas", json={"name": "Non", "team": "equipe-a"}).status_code == 403
    login(client, world.stranger)
    assert client.post("/api/areas", json={"name": "Non"}).status_code == 403

    login(client, world.admin)  # l'administrateur, avec ou sans équipe
    assert client.post("/api/areas", json={"name": "Libre"}).json()["teams"] == []
    assert [t["slug"] for t in client.post("/api/areas", json={"name": "Chez B", "team": "equipe-b"}).json()["teams"]] == ["equipe-b"]


def test_a_team_is_attached_by_an_admin_or_by_its_manager(client):
    world = team_world(client)
    login(client, world.manager_a)
    # le manager de A ne rattache pas B : seul le manager de B, ou un admin, le fait
    assert client.post("/api/areas/theme-a/teams", json={"team": "equipe-b"}).status_code == 403
    assert client.post("/api/areas/theme-a/teams", json={"team": "inconnue"}).status_code == 422
    # le patch du projet ne parle plus d'équipe
    assert [t["slug"] for t in get_area(client, "theme-a")["teams"]] == ["equipe-a"]

    login(client, world.manager_b)
    area = client.post("/api/areas/theme-a/teams", json={"team": "equipe-b"})  # B rejoint de sa propre initiative
    assert area.status_code == 201
    assert [t["slug"] for t in area.json()["teams"]] == ["equipe-a", "equipe-b"]
    assert client.post("/api/areas/theme-a/teams", json={"team": "equipe-b"}).status_code == 201  # sans effet
    assert client.patch("/api/areas/theme-a", json={"description": "Revu par B"}).status_code == 200  # B y est manager
    login(client, world.manager_a)
    assert client.patch("/api/areas/theme-a", json={"description": "Revu par A"}).status_code == 200  # A aussi

    # B se retire ; un manager de A ne retire pas B
    assert client.delete("/api/areas/theme-a/teams/equipe-b").status_code == 403
    login(client, world.manager_b)
    assert [t["slug"] for t in client.delete("/api/areas/theme-a/teams/equipe-b").json()["teams"]] == ["equipe-a"]
    assert client.patch("/api/areas/theme-a", json={"description": "x"}).status_code == 403

    # le thème système n'a pas d'équipe
    login(client, world.admin)
    assert client.post("/api/areas/non-classe/teams", json={"team": "equipe-a"}).status_code == 409


def test_a_team_cannot_leave_an_area_where_it_still_owns_things(client):
    world = team_world(client)  # l'équipe A possède la thématique « t » et le µprojet « recuit » dans theme-a
    login(client, world.manager_a)
    refused = client.delete("/api/areas/theme-a/teams/equipe-a")
    assert refused.status_code == 409 and refused.json()["code"] == "team_has_content"


def test_areas_are_listed_by_team(client):
    team_world(client)
    assert [a["slug"] for a in assert_ok(client.get("/api/areas", params={"team": "equipe-a"}))] == ["theme-a"]
    assert assert_ok(client.get("/api/areas", params={"team": "equipe-b"})) == []
    assert client.get("/api/areas", params={"team": "inconnue"}).status_code == 404
