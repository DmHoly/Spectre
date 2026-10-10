from __future__ import annotations

from support.accounts import login
from support.areas import create_thematic
from support.experiments import conclude, launch
from support.http import assert_ok
from support.lots import create_lot
from support.microprojects import create_microproject
from support.teams import team_world


def _board(client, team_slug=None):
    return assert_ok(client.get(f"/api/team-plannings/{team_slug}" if team_slug else "/api/team-plannings"))


def _microproject(board, slug):
    return next(mp for group in board["groups"] for mp in group["microprojects"] if mp["slug"] == slug)


def test_a_manager_reads_the_wafers_of_the_team_by_thematic_microproject_and_study(client):
    world = team_world(client)
    create_thematic(client, "theme-a", "Coquilles")
    login(client, world.manager_a)
    create_microproject(client, "Contacts", area="theme-a", thematic="coquilles")
    first = launch(client, "contacts", title="Épi E-231", entities=[{"sample_id": "W12-A3"}, {"sample_id": "W12-A4"}])
    conclude(client, "contacts", first["id"], decision="promote", summary="ok")
    launch(client, "contacts", title="Épi E-232", entities=[{"sample_id": "W13-B1"}, {}])
    launch(client, "recuit", title="Recuit 1", entities=[{"sample_id": "W20"}])
    client.post("/api/microprojects/contacts/experiment-plans", json={"title": "Prochaine épi", "mode": "new_wafers", "wafer_count": 4})

    board = _board(client)
    assert board["team"] == {"slug": "equipe-a", "name": "Équipe A"}
    assert [t["slug"] for t in board["teams"]] == ["equipe-a"]  # managed teams only
    assert [a["slug"] for a in board["areas"]] == ["theme-a"]

    # thématique ▸ µprojet ; « recuit » has no thématique: it sits in the area's loose group
    by_name = {(g["thematic"] or {}).get("name"): [mp["slug"] for mp in g["microprojects"]] for g in board["groups"]}
    assert by_name == {"Coquilles": ["contacts"], None: ["recuit"]}

    contacts = _microproject(board, "contacts")
    assert [s["title"] for s in contacts["studies"]] == ["Épi E-231", "Épi E-232"]
    done, running = contacts["studies"]
    assert done["status"] == "concluded" and done["decision"] == "promote" and done["ended_at"]
    assert [w["key"] for w in done["wafers"]] == ["W12A3", "W12A4"]
    # a place still to map shows as a row without lasermark
    assert [(w["lasermark"], w["key"]) for w in running["wafers"]] == [("W13-B1", "W13B1"), (None, None)]
    assert running["url"] == f"/microprojets/contacts/experiences/{running['id']}"
    assert [(p["title"], p["wafer_count"]) for p in contacts["plans"]] == [("Prochaine épi", 4)]


def test_lots_of_the_team_wafers_come_with_their_wafer_keys_and_planned_ones_too(client):
    world = team_world(client)
    login(client, world.manager_a)
    launch(client, "recuit", title="Recuit 1", entities=[{"sample_id": "W20"}, {"sample_id": "W21"}])
    running = create_lot(client, "L-RUN", started_on="2026-01-05", wafers=["W20"])
    planned = create_lot(client, title="Prochain run", priority="P20", wafers=["w21", "X99"], forecast_exit_on="2099-01-01")
    create_lot(client, "L-OTHER", wafers=["Z1"])  # nothing of the team

    lots = {lot["code"]: lot for lot in _board(client)["lots"]}
    assert set(lots) == {"L-RUN", planned["code"]}
    assert lots["L-RUN"]["status"] == "wip" and lots["L-RUN"]["wafers"] == ["W20"]
    assert lots[planned["code"]]["status"] == "planned" and lots[planned["code"]]["wafers"] == ["W21", "X99"]
    assert lots[planned["code"]]["url"] == f"/lots/{planned['code']}" and running["id"] == lots["L-RUN"]["id"]


def test_the_planning_is_for_the_team_managers_and_the_admins(client):
    world = team_world(client)

    login(client, world.member_a)
    empty = _board(client)
    assert empty["team"] is None and empty["teams"] == [] and empty["groups"] == []
    refused = client.get("/api/team-plannings/equipe-a")
    assert refused.status_code == 403 and refused.json()["code"] == "planning_forbidden"

    login(client, world.manager_b)
    assert client.get("/api/team-plannings/equipe-a").status_code == 403
    assert _board(client)["team"]["slug"] == "equipe-b"

    login(client, world.admin)
    assert [t["slug"] for t in _board(client)["teams"]] == ["equipe-a", "equipe-b"]
    assert _board(client, "equipe-a")["team"]["slug"] == "equipe-a"
    assert client.get("/api/team-plannings/inconnue").status_code == 404

    client.post("/api/sessions/current/logout")
    client.cookies.clear()
    assert client.get("/api/team-plannings").status_code == 401


def test_the_planning_page_is_served(client):
    world = team_world(client)
    login(client, world.manager_a)
    assert client.get("/planning").status_code == 200
    assert client.get("/planning/equipe-a").status_code == 200
