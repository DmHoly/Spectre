from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date

import pytest

from support.accounts import login, signup
from support.areas import create_thematic
from support.experiments import conclude, launch, lineage
from support.http import assert_handler_404
from support.lots import (
    add_wafers,
    create_lot,
    delete_lot,
    find_lot,
    get_lot,
    list_lots,
    lot_url,
    patch_lot,
    remove_wafer,
    set_thematics,
    update_lot,
)
from support.microprojects import create_microproject

TODAY = date.today().isoformat()


def _signup_boss(client):
    signup(client, "boss@example.com", name="Alice Martin")  # the first account: an admin


def _thematic_id(client, name):
    return next(t["id"] for t in client.get("/api/thematics").json() if t["name"] == name)


def test_a_lot_gets_a_code_a_priority_its_dates_and_its_wafers(client):
    _signup_boss(client)
    response = client.post(
        "/api/lots",
        json={"title": "Run EBL", "priority": "p20", "wafers": ["W12-A3", "w12 a3", "W12-A4"], "forecast_exit_on": "2099-12-15"},
    )
    assert response.status_code == 201
    lot = response.json()
    assert response.headers["Location"] == lot_url(lot["id"]) and response.headers["ETag"] == f'"{lot["updated_at"]}"'
    assert lot["code"] == "LOT-0001" and lot["priority"] == "P20" and lot["source"] == "declaratif"
    assert lot["status"] == "planned" and lot["is_active"] is True  # no start yet
    # « w12 a3 » = le même wafer ; chaque wafer porte sa clé
    assert [(w["key"], w["lasermark"]) for w in lot["wafers"]] == [("W12A3", "W12-A3"), ("W12A4", "W12-A4")]
    assert lot["can_delete"] is True
    assert "steps" not in lot  # no route: priority and dates only

    started = create_lot(client, "L2", started_on=TODAY)
    assert started["status"] == "wip"  # started: in progress
    bad = client.post("/api/lots", json={"code": "L3", "started_on": "2026-05-01", "forecast_exit_on": "2026-04-01"})
    assert bad.status_code == 422
    assert client.post("/api/lots", json={"code": "/ pas un code"}).status_code == 422


def test_a_code_already_taken_is_a_conflict(client):
    _signup_boss(client)
    create_lot(client, "LOT-0001", title="Run EBL")
    duplicate = client.post("/api/lots", json={"code": "lot-0001"})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "lot_code_taken"
    assert find_lot(client, "lot-0001")["title"] == "Run EBL"  # le code se retrouve sans la casse

    other = create_lot(client, "L2")
    renamed = patch_lot(client, other["id"], code="Lot-0001")
    assert renamed.status_code == 409 and renamed.json()["code"] == "lot_code_taken"


def test_a_code_taken_during_the_creation_is_a_conflict_too(client, monkeypatch):
    # Deux créations simultanées du même code : la seconde passe la vérification avant que la
    # première n'écrive, puis bute sur l'index unique - 409 et non 500.
    from spectre.kernel.db import db_path
    from spectre.plugins.lots import service

    _signup_boss(client)
    check_priority = service._check_priority

    def racing(priority):
        conn = sqlite3.connect(db_path())
        conn.execute("INSERT INTO lots (code) VALUES ('RACE')")
        conn.commit()
        conn.close()
        return check_priority(priority)

    monkeypatch.setattr(service, "_check_priority", racing)
    response = client.post("/api/lots", json={"code": "race"})
    assert response.status_code == 409 and response.json()["code"] == "lot_code_taken"


def test_lots_created_at_once_without_a_code_each_get_their_own(client, monkeypatch):
    # Huit créations simultanées sans code : chacune reçoit un numéro, aucune ne se voit opposer
    # un 409 pour un code qu'elle n'a pas saisi.
    from spectre.plugins.accounts import service as accounts
    from spectre.plugins.lots import service

    _signup_boss(client)
    boss = accounts.get_by_email("boss@example.com").id
    next_code = service._next_code

    def slow_next_code(conn):
        code = next_code(conn)
        time.sleep(0.02)  # élargit la fenêtre entre le choix du numéro et l'écriture
        return code

    monkeypatch.setattr(service, "_next_code", slow_next_code)
    barrier = threading.Barrier(8)
    codes: list[str] = []
    errors: list[BaseException] = []

    def create() -> None:
        try:
            barrier.wait()
            codes.append(service.create(code=None, created_by=boss).code)
        except BaseException as exc:  # noqa: BLE001 - remonté au thread principal
            errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert sorted(codes) == [f"LOT-{n:04d}" for n in range(1, 9)]


def test_a_generated_code_taken_meanwhile_moves_on_to_the_next(client, monkeypatch):
    # Un code saisi à la main qui prend le numéro choisi juste avant l'écriture : le lot sans code
    # passe au suivant au lieu d'un 409.
    from spectre.kernel.db import db_path
    from spectre.plugins.lots import service

    _signup_boss(client)
    next_code = service._next_code
    calls = []

    def racing(conn):
        code = next_code(conn)
        if not calls:
            other = sqlite3.connect(db_path())
            other.execute("INSERT INTO lots (code) VALUES (?)", (code.lower(),))
            other.commit()
            other.close()
        calls.append(code)
        return code

    monkeypatch.setattr(service, "_next_code", racing)
    response = client.post("/api/lots", json={})
    assert response.status_code == 201 and response.json()["code"] == "LOT-0002"


def test_lots_are_listed_by_priority_and_filtered_by_status(client):
    _signup_boss(client)
    for code, priority, forecast in (("A", "P30", "2099-01-01"), ("B", "P10", "2099-03-01"), ("C", "", "2099-01-01"), ("D", "P10", "2099-02-01")):
        create_lot(client, code, priority=priority, forecast_exit_on=forecast)
    update_lot(client, find_lot(client, "C")["id"], status="cancelled")

    assert [l["code"] for l in list_lots(client)] == ["D", "B", "A", "C"]  # P10 first, then the soonest exit
    assert [l["code"] for l in list_lots(client, status="planned,wip,hold")] == ["D", "B", "A"]
    assert [l["code"] for l in list_lots(client, status="cancelled")] == ["C"]
    refused = client.get("/api/lots", params={"status": "actifs"})
    assert refused.status_code == 422 and "actifs" in refused.json()["detail"]
    assert client.get("/api/lots", params={"view": "gantt"}).status_code == 422
    assert client.get("/api/lot-priorities").json()[0] == "P10"


def test_the_summary_view_is_light(client):
    _signup_boss(client)
    create_lot(client, "S1", priority="P10", wafers=["W1"])
    (summary,) = list_lots(client, view="summary")
    assert summary == {
        "id": summary["id"],
        "code": "S1",
        "title": "",
        "priority": "P10",
        "status": "planned",
        "is_active": True,
        "source": "declaratif",
        "forecast_exit_on": None,
        "exited_on": None,
        "wafers": [{"key": "W1", "lasermark": "W1"}],
    }


def test_lots_are_found_by_the_keys_of_their_wafers(client):
    _signup_boss(client)
    create_lot(client, "A", wafers=["W12-A3", "W7"])
    create_lot(client, "B", wafers=["w12 a3"])
    create_lot(client, "C", wafers=["W9"])
    assert [l["code"] for l in list_lots(client, wafer="W12A3")] == ["A", "B"]
    assert [l["code"] for l in list_lots(client, wafer="w7,W9", view="summary")] == ["A", "C"]
    assert list_lots(client, wafer="INCONNU") == [] and list_lots(client, wafer=",") == []
    assert [l["code"] for l in list_lots(client, wafer="W12A3", code="b")] == ["B"]


def test_declaring_the_end_of_a_lot_and_its_gap_to_the_forecast(client):
    _signup_boss(client)
    lot_id = create_lot(client, "L1", started_on="2026-01-05", forecast_exit_on="2026-03-01")["id"]
    lot = get_lot(client, lot_id)
    assert lot["status"] == "wip" and lot["planned_days"] == 55 and lot["late_days"] > 0  # forecast passed, not out

    lot = update_lot(client, lot_id, exited_on="2026-03-04")
    assert lot["status"] == "done" and lot["is_active"] is False and lot["exited_on"] == "2026-03-04"  # a declared end means « out »
    assert lot["exit_delta_days"] == 3 and lot["late_days"] is None and lot["elapsed_days"] == 58
    assert lot["started_on"] == "2026-01-05" and lot["forecast_exit_on"] == "2026-03-01"  # untouched: only what was sent changes
    assert [l["code"] for l in list_lots(client, status="done")] == ["L1"]

    reopened = update_lot(client, lot_id, status="wip")
    assert reopened["status"] == "wip" and reopened["exited_on"] is None  # reopening clears the declared end
    out_today = update_lot(client, lot_id, status="done")
    assert out_today["exited_on"] == TODAY  # « out » without a date: today
    assert update_lot(client, lot_id, exited_on=None)["status"] == "wip"  # clearing the declared end reopens it
    assert patch_lot(client, lot_id, exited_on="2025-12-01").status_code == 422  # ends before it starts


def test_the_status_rules_are_one_pure_function():
    from spectre.plugins.lots.service import declared_state

    today = "2026-10-03"
    running, out = ("wip", "2026-01-01", None), ("done", "2026-01-01", "2026-03-04")
    assert declared_state(running, {"exited_on": "2026-03-04"}, today=today) == out  # a declared end: out
    assert declared_state(running, {"status": "wip", "exited_on": "2026-03-04"}, today=today) == out  # the date wins
    assert declared_state(running, {"status": "done"}, today=today) == ("done", "2026-01-01", today)  # out today
    assert declared_state(out, {"status": "wip"}, today=today) == running  # reopened
    assert declared_state(out, {"exited_on": None}, today=today) == running  # reopened too
    assert declared_state(out, {"status": "cancelled"}, today=today) == ("cancelled", "2026-01-01", "2026-03-04")
    assert declared_state(out, {"title": "x"}, today=today) == out
    assert declared_state(("planned", None, None), {"status": "hold"}, today=today) == ("hold", today, None)
    assert declared_state(("planned", None, None), {}, today=today) == ("planned", None, None)


def test_a_lot_on_hold(client):
    _signup_boss(client)
    lot_id = create_lot(client, "L1", forecast_exit_on="2020-01-01")["id"]
    lot = update_lot(client, lot_id, status="hold", hold_reason="Bâti en panne")
    assert lot["status"] == "hold" and lot["hold_reason"] == "Bâti en panne" and lot["late_days"] > 0
    assert lot["started_on"] == TODAY  # on hold = it had started
    assert update_lot(client, lot_id, status="wip")["hold_reason"] == ""  # the reason goes with the pause
    refused = patch_lot(client, lot_id, status="nope")
    assert refused.status_code == 422 and "nope" in refused.json()["detail"]


def test_a_stale_version_is_refused_and_a_no_op_changes_nothing(client):
    _signup_boss(client)
    lot = create_lot(client, "L1", title="Avant")
    response = client.get(lot_url(lot["id"]))
    shown = response.json()["updated_at"]
    assert response.headers["ETag"] == f'"{shown}"'

    edited = update_lot(client, lot["id"], if_match=shown, title="Après")
    assert edited["title"] == "Après" and edited["updated_at"] != shown

    stale = patch_lot(client, lot["id"], if_match=shown, title="Perdu")
    assert stale.status_code == 412 and stale.json()["code"] == "stale_version"
    assert get_lot(client, lot["id"])["title"] == "Après"  # nothing written

    same = update_lot(client, lot["id"], if_match=edited["updated_at"], title="Après", priority="")
    assert same["updated_at"] == edited["updated_at"]  # no change, no new version
    assert update_lot(client, lot["id"])["updated_at"] == edited["updated_at"]  # an empty PATCH either


def test_a_lot_fed_by_prism_keeps_its_priority_dates_and_wafers(client):
    from spectre.kernel.db import get_conn

    _signup_boss(client)
    lot = create_lot(client, "P1", priority="P10", forecast_exit_on="2099-01-01", wafers=["W1"])
    with get_conn() as conn:
        conn.execute("UPDATE lots SET source = 'prism' WHERE id = ?", (lot["id"],))

    for change in ({"priority": "P20"}, {"forecast_exit_on": "2099-02-01"}, {"exited_on": "2099-01-02"}):
        refused = patch_lot(client, lot["id"], **change)
        assert refused.status_code == 409 and refused.json()["code"] == "lot_read_only_source", change
    assert client.post(f"{lot_url(lot['id'])}/wafers", json={"lasermarks": ["W2"]}).status_code == 409
    assert client.delete(f"{lot_url(lot['id'])}/wafers/W1").status_code == 409

    # le reste se saisit ici, sans les règles de statut d'une saisie déclarative
    edited = update_lot(client, lot["id"], title="Run PRISM", priority="P10", status="done")
    assert edited["title"] == "Run PRISM" and edited["status"] == "done" and edited["exited_on"] is None
    with pytest.raises(sqlite3.IntegrityError):  # aucune autre source
        with get_conn() as conn:
            conn.execute("UPDATE lots SET source = 'excel' WHERE id = ?", (lot["id"],))


def test_an_unknown_lot_is_404(client):
    _signup_boss(client)
    assert_handler_404(client.get(lot_url(999)))
    assert_handler_404(client.patch(lot_url(999), json={"status": "wip"}))
    assert_handler_404(client.delete(lot_url(999)))
    assert_handler_404(client.post(f"{lot_url(999)}/wafers", json={"lasermarks": ["W1"]}))
    assert_handler_404(client.put(f"{lot_url(999)}/thematics", json={"thematic_ids": []}))
    assert list_lots(client, code="INCONNU") == []


def test_wafers_come_and_go(client):
    _signup_boss(client)
    lot = create_lot(client, "L1", wafers=["W1"])
    added = add_wafers(client, lot["id"], ["w1", "W2", "W-3"])
    assert [w["lasermark"] for w in added["wafers"]] == ["W1", "W2", "W-3"]
    again = client.post(f"{lot_url(lot['id'])}/wafers", json={"lasermarks": ["W2"]})
    assert again.status_code == 200 and again.json()["updated_at"] == added["updated_at"]  # nothing new: nothing written

    remove_wafer(client, lot["id"], "W3")  # by its key
    assert [w["key"] for w in get_lot(client, lot["id"])["wafers"]] == ["W1", "W2"]
    assert_handler_404(client.delete(f"{lot_url(lot['id'])}/wafers/W3"), "W3")


def test_a_lot_finds_its_experiments_and_thematics_through_its_wafers(client):
    _signup_boss(client)
    create_thematic(client, "native-pt2", "Dopage PGaN")
    create_thematic(client, "native-pt2", "Double EBL")
    create_microproject(client, "Recuit Mg", area="native-pt2", thematic="dopage-pgan")
    launched = launch(client, "recuit-mg", title="Recuit 700 C", entities=[{"sample_id": "W12-A3"}])
    lot = create_lot(client, "L7", wafers=["w12-a3", "W99"], thematic_ids=[_thematic_id(client, "Double EBL")])

    lot = get_lot(client, lot["id"])
    (experiment,) = lot["experiments"]
    assert (experiment["id"], experiment["title"], experiment["wafers"], experiment["member"]) == (launched["id"], "Recuit 700 C", ["w12-a3"], True)
    assert experiment["status"] == "draft" and experiment["started_at"]
    assert {t["name"]: (t["declared"], t["via_experiments"]) for t in lot["thematics"]} == {
        "Dopage PGaN": (False, True),
        "Double EBL": (True, False),
    }
    assert lot["wafers"][0]["experiments"][0]["title"] == "Recuit 700 C"
    assert lot["wafers"][1] == {"key": "W99", "lasermark": "W99", "experiments": []}

    # The lineage no longer carries the lots: the page asks the lots of the node's wafers.
    node = lineage(client, "recuit-mg")["nodes"][0]
    assert "lots" not in node and node["wafers"] == ["W12-A3"]
    assert [(l["code"], l["is_active"]) for l in list_lots(client, wafer="W12A3", view="summary")] == [("L7", True)]

    # Someone outside the µprojet sees the experiment's dates and status, not what it is.
    signup(client, "hand@example.com", name="Bob")
    lot = get_lot(client, lot["id"])
    other = lot["experiments"][0]
    assert "title" not in other and "id" not in other and other["member"] is False
    assert other["status"] == "draft" and other["started_at"] and other["microproject"]["code"] == "Nat_0001"
    assert lot["wafers"][0]["experiments"] == [{"microproject": other["microproject"], "member": False}]
    assert lot["can_delete"] is False


def test_declared_thematics_are_replaced_as_a_whole(client):
    _signup_boss(client)
    create_thematic(client, "native-pt2", "Dopage PGaN")
    create_thematic(client, "native-pt2", "Double EBL")
    lot = create_lot(client, "L1")
    dopage, ebl = _thematic_id(client, "Dopage PGaN"), _thematic_id(client, "Double EBL")
    assert [t["name"] for t in set_thematics(client, lot["id"], [ebl, dopage, ebl])["thematics"]] == ["Dopage PGaN", "Double EBL"]
    assert [t["name"] for t in set_thematics(client, lot["id"], [ebl])["thematics"]] == ["Double EBL"]
    refused = client.put(f"{lot_url(lot['id'])}/thematics", json={"thematic_ids": [ebl, 999]})
    assert refused.status_code == 422
    assert [t["name"] for t in get_lot(client, lot["id"])["thematics"]] == ["Double EBL"]  # nothing written


def test_lots_are_found_by_code_title_or_wafer(client):
    _signup_boss(client)
    create_lot(client, "L24-012", title="Run puits multiples", wafers=["W12-A3"])
    create_lot(client, "L24-013", title="Épitaxie longue")
    create_lot(client, "X-1", title="Autre", wafers=["W12-A30"])

    def codes(q, **params):
        return [l["code"] for l in list_lots(client, q=q, view="summary", **params)]

    assert codes("L24-012") == ["L24-012"]
    assert codes("l24") == ["L24-012", "L24-013"]
    assert codes("puits") == ["L24-012"]
    assert codes("épitaxie") == ["L24-013"]  # accents and case, the whole of Unicode
    assert codes("w12a3") == ["L24-012", "X-1"]  # the exact wafer first, then the ones starting with it
    assert codes("x") == []
    assert codes("w12a3", status="cancelled") == []


def test_only_the_creator_or_an_admin_deletes_a_lot(client):
    _signup_boss(client)  # admin
    signup(client, "hand@example.com", name="Bob")
    lot = create_lot(client, "B1")
    signup(client, "third@example.com", name="Chloé")
    assert client.delete(lot_url(lot["id"])).status_code == 403
    assert update_lot(client, lot["id"], status="wip", priority="P10")["priority"] == "P10"  # anyone updates
    login(client, "boss@example.com")
    delete_lot(client, lot["id"])
    assert_handler_404(client.get(lot_url(lot["id"])))
    assert client.get("/lots").status_code == 200 and client.get("/lots/B1").status_code == 200  # the pages


def test_an_experiment_is_attached_as_soon_as_its_wafer_enters_a_lot_even_if_finished(client):
    # An epitaxy test is over, then a fabrication lot is launched on its wafer for the electro-optical
    # data: the finished experiment belongs to that lot.
    _signup_boss(client)
    create_microproject(client, "Recuit Mg", area="native-pt2")
    launched = launch(client, "recuit-mg", title="Epitaxie 700 C", entities=[{"sample_id": "W12-A3"}])
    conclude(client, "recuit-mg", launched["id"], decision="promote")
    lot = create_lot(client, "LATER", started_on="2099-01-01", wafers=["W12-A3"])

    lot = get_lot(client, lot["id"])
    assert [(e["title"], e["decision"]) for e in lot["experiments"]] == [("Epitaxie 700 C", "promote")]
    assert lot["experiments"][0]["ended_at"]
    assert lot["wafers"][0]["experiments"][0]["title"] == "Epitaxie 700 C"
    assert [l["code"] for l in list_lots(client, wafer="W12-A3")] == ["LATER"]


def test_the_lot_picker_of_a_microprojet_lists_lots_one_can_add_a_wafer_to(client):
    # « Ajouter au lot » from a µprojet, at any time: lots still running (P10 first), then the ones
    # already out - never the cancelled ones -, with their wafers (to tell which already hold it).
    _signup_boss(client)
    create_lot(client, "B", priority="P20", wafers=["W1"])
    a = create_lot(client, "A", priority="P10")
    out = create_lot(client, "OUT", priority="P30")
    update_lot(client, out["id"], status="done", exited_on=TODAY)
    gone = create_lot(client, "GONE")
    update_lot(client, gone["id"], status="cancelled")

    choices = list_lots(client, status="planned,wip,hold,done", view="summary")
    assert [(c["code"], c["is_active"], [w["key"] for w in c["wafers"]]) for c in choices] == [
        ("A", True, []),
        ("B", True, ["W1"]),
        ("OUT", False, []),
    ]
    added = add_wafers(client, a["id"], ["W1"])
    assert [w["lasermark"] for w in added["wafers"]] == ["W1"]  # a wafer may sit in two lots
    again = add_wafers(client, out["id"], ["W2"])  # a lot already out takes a wafer too
    assert [w["lasermark"] for w in again["wafers"]] == ["W2"]
    assert [l["code"] for l in list_lots(client, wafer="W1")] == ["A", "B"]
