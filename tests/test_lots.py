from __future__ import annotations

from datetime import date

from support.accounts import login, signup
from support.experiments import conclude, launch, lineage
from support.http import assert_handler_404
from support.lots import create_lot, get_lot, update_lot
from support.management import create_thematique
from support.microprojects import create_microproject


def _signup_boss(client):
    signup(client, "boss@example.com", name="Alice Martin")  # the first account: an admin


def test_a_lot_gets_a_code_a_priority_its_dates_and_its_wafers(client):
    _signup_boss(client)
    created = client.post(
        "/api/lots",
        json={"title": "Run EBL", "priority": "p20", "wafers": ["W12-A3", "w12 a3", "W12-A4"], "forecast_exit_on": "2099-12-15"},
    )
    assert created.status_code == 201
    lot = created.json()
    assert lot["code"] == "LOT-0001" and lot["priority"] == "P20" and lot["source"] == "declaratif"
    assert lot["status"] == "planned"  # no start yet
    assert [w["lasermark"] for w in lot["wafers"]] == ["W12-A3", "W12-A4"]  # « w12 a3 » = le même wafer
    assert "steps" not in lot  # no route: priority and dates only

    duplicate = client.post("/api/lots", json={"code": "lot-0001"})
    assert duplicate.status_code == 422
    assert get_lot(client, "lot-0001")["title"] == "Run EBL"  # le code se retrouve sans la casse
    started = create_lot(client, "L2", started_on=date.today().isoformat())
    assert started["status"] == "wip"  # started: in progress
    bad = client.post("/api/lots", json={"code": "L3", "started_on": "2026-05-01", "forecast_exit_on": "2026-04-01"})
    assert bad.status_code == 422


def test_lots_are_listed_by_priority(client):
    _signup_boss(client)
    for code, priority, forecast in (("A", "P30", "2099-01-01"), ("B", "P10", "2099-03-01"), ("C", "", "2099-01-01"), ("D", "P10", "2099-02-01")):
        create_lot(client, code, priority=priority, forecast_exit_on=forecast)
    body = client.get("/api/lots").json()
    assert [l["code"] for l in body["lots"]] == ["D", "B", "A", "C"]  # P10 first, then the soonest exit
    assert body["priorities"][0] == "P10"


def test_declaring_the_end_of_a_lot_and_its_gap_to_the_forecast(client):
    _signup_boss(client)
    create_lot(client, "L1", started_on="2026-01-05", forecast_exit_on="2026-03-01")
    lot = get_lot(client, "L1")
    assert lot["status"] == "wip" and lot["planned_days"] == 55 and lot["late_days"] > 0  # forecast passed, not out

    out = {"code": "L1", "status": "wip", "started_on": "2026-01-05", "forecast_exit_on": "2026-03-01", "exited_on": "2026-03-04"}
    lot = client.put("/api/lots/L1", json=out).json()
    assert lot["status"] == "done" and lot["exited_on"] == "2026-03-04"  # a declared end means « out »
    assert lot["exit_delta_days"] == 3 and lot["late_days"] is None and lot["elapsed_days"] == 58
    assert [l["code"] for l in client.get("/api/lots?statut=sortis").json()["lots"]] == ["L1"]

    reopened = client.put("/api/lots/L1", json={**out, "status": "wip", "exited_on": None}).json()
    assert reopened["status"] == "wip" and reopened["exited_on"] is None
    bad = client.put("/api/lots/L1", json={**out, "exited_on": "2025-12-01"})
    assert bad.status_code == 422  # ends before it starts


def test_a_lot_on_hold(client):
    _signup_boss(client)
    create_lot(client, "L1", forecast_exit_on="2020-01-01")
    lot = update_lot(client, "L1", status="hold", hold_reason="Bâti en panne", forecast_exit_on="2020-01-01")
    assert lot["status"] == "hold" and lot["hold_reason"] == "Bâti en panne" and lot["late_days"] > 0
    assert lot["started_on"] == date.today().isoformat()  # on hold = it had started
    assert client.put("/api/lots/L1", json={"code": "L1", "status": "nope"}).status_code == 422


def test_an_unknown_lot_is_404(client):
    _signup_boss(client)
    assert_handler_404(client.get("/api/lots/INCONNU"))
    assert_handler_404(client.put("/api/lots/INCONNU", json={"code": "INCONNU", "status": "wip"}))
    assert_handler_404(client.post("/api/lots/INCONNU/wafers", json={"lasermarks": ["W1"]}))


def test_a_lot_finds_its_experiences_and_thematiques_through_its_wafers(client):
    _signup_boss(client)
    create_thematique(client, "native-pt2", "Dopage PGaN")
    create_thematique(client, "native-pt2", "Double EBL")
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2", thematique_slug="dopage-pgan")
    launched = launch(client, "recuit-mg", title="Recuit 700 C", entities=[{"sample_id": "W12-A3"}])
    ebl = next(t["id"] for g in client.get("/api/lots/thematiques").json() for t in g["thematiques"] if t["name"] == "Double EBL")
    create_lot(client, "L7", wafers=["w12-a3", "W99"], thematic_ids=[ebl])

    lot = get_lot(client, "L7")
    assert [(e["id"], e["title"], e["wafers"]) for e in lot["experiences"]] == [(launched["id"], "Recuit 700 C", ["w12-a3"])]
    assert {t["name"]: (t["declared"], t["via_experiences"]) for t in lot["thematiques"]} == {
        "Dopage PGaN": (False, True),
        "Double EBL": (True, False),
    }
    assert lot["wafers"][1] == {"lasermark": "W99", "experiences": []}

    # The badge beside the experience's node in the µprojet's graph, and the plate's page.
    node = lineage(client, "recuit-mg")["nodes"][0]
    assert node["lots"] == [{"code": "L7", "status": "planned"}]
    assert [l["code"] for l in client.get("/api/plaques/W12-A3").json()["lots"]] == ["L7"]

    # Someone outside the µprojet sees the experience's dates and status, not what it is.
    signup(client, "hand@example.com", name="Bob")
    other = get_lot(client, "L7")["experiences"][0]
    assert "title" not in other and "id" not in other and other["member"] is False
    assert other["microproject"]["code"] == "Nat_0001"


def test_lots_are_found_by_code_title_or_wafer(client):
    _signup_boss(client)
    create_lot(client, "L24-012", title="Run puits multiples", wafers=["W12-A3"])
    create_lot(client, "L24-013", title="Autre")

    def codes(q):
        return [(h["code"], h["wafer"]) for h in client.get(f"/api/lots/recherche?q={q}").json()]

    assert codes("L24-012") == [("L24-012", None)]
    assert codes("l24") == [("L24-012", None), ("L24-013", None)]
    assert codes("puits") == [("L24-012", None)]
    assert codes("w12a3") == [("L24-012", "W12-A3")]
    assert codes("x") == []


def test_only_the_creator_or_an_admin_deletes_a_lot(client):
    _signup_boss(client)  # admin
    signup(client, "hand@example.com", name="Bob")
    create_lot(client, "B1")
    signup(client, "third@example.com", name="Chloé")
    assert client.delete("/api/lots/B1").status_code == 403
    assert client.put("/api/lots/B1", json={"code": "B1", "status": "wip", "priority": "P10"}).status_code == 200  # anyone updates
    login(client, "boss@example.com")
    assert client.delete("/api/lots/B1").status_code == 200
    assert_handler_404(client.get("/api/lots/B1"))
    assert client.get("/lots").status_code == 200 and client.get("/lots/B1").status_code == 200  # the pages


def test_an_experiment_is_attached_as_soon_as_its_wafer_enters_a_lot_even_if_finished(client):
    # An epitaxy test is over, then a fabrication lot is launched on its wafer for the electro-optical
    # data: the finished experiment belongs to that lot.
    _signup_boss(client)
    create_microproject(client, "Recuit Mg", management_area_slug="native-pt2")
    launched = launch(client, "recuit-mg", title="Epitaxie 700 C", entities=[{"sample_id": "W12-A3"}])
    conclude(client, "recuit-mg", launched["id"], decision="promote")
    create_lot(client, "LATER", started_on="2099-01-01", wafers=["W12-A3"])

    lot = get_lot(client, "LATER")
    assert [e["title"] for e in lot["experiences"]] == ["Epitaxie 700 C"]
    assert lot["wafers"][0]["experiences"][0]["title"] == "Epitaxie 700 C"
    node = lineage(client, "recuit-mg")["nodes"][0]
    assert [l["code"] for l in node["lots"]] == ["LATER"]
    assert [l["code"] for l in client.get("/api/plaques/W12-A3").json()["lots"]] == ["LATER"]


def test_a_lot_table_from_the_first_version_gets_its_priority_column(data_dir):
    # The very first lots table (with a route of steps) had no priority: init_db adds it.
    import sqlite3

    from spectre.core import db

    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute(
        "CREATE TABLE lots (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', "
        "description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned', started_on TEXT, forecast_exit_on TEXT, "
        "exited_on TEXT, hold_reason TEXT NOT NULL DEFAULT '', current_step_id INTEGER, source TEXT NOT NULL DEFAULT 'declaratif', "
        "created_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO lots (code) VALUES ('OLD-1')")
    conn.commit()
    conn.close()

    db.init_db()
    from spectre.core import lots

    assert lots.get_by_code("OLD-1").priority == ""


def test_the_lot_picker_of_a_microprojet_lists_lots_one_can_add_a_wafer_to(client):
    # « Ajouter au lot » from a µprojet, at any time: lots still running (P10 first), then the ones
    # already out - never the cancelled ones -, with their wafers (to tell which already hold it).
    _signup_boss(client)
    create_lot(client, "B", priority="P20", wafers=["W1"])
    create_lot(client, "A", priority="P10")
    create_lot(client, "OUT", priority="P10")
    update_lot(client, "OUT", status="done", exited_on=date.today().isoformat())
    create_lot(client, "GONE")
    update_lot(client, "GONE", status="cancelled")

    choices = client.get("/api/lots/selection").json()
    assert [(c["code"], c["wafers"]) for c in choices] == [("A", []), ("B", ["W1"]), ("OUT", [])]
    added = client.post("/api/lots/A/wafers", json={"lasermarks": ["W1"]}).json()
    assert [w["lasermark"] for w in added["wafers"]] == ["W1"]  # a wafer may sit in two lots

    again = client.post("/api/lots/OUT/wafers", json={"lasermarks": ["W2"]}).json()  # a lot already out takes a wafer too
    assert [w["lasermark"] for w in again["wafers"]] == ["W2"]
