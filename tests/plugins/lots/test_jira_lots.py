"""Les lots JIRA (spectre.plugins.lots.jira) : les noms de lot des FDL lus comme la vie d'une plaque
les lit, la liste des lots à importer, l'import (le lot, ses plaques, leurs fiches) et la détection
automatique quand la vie d'une plaque est lue. La démo répond à la place de PRISM."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from spectre.plugins.lots import jira
from spectre.plugins.wafers import tracking_source

from support.accounts import signup
from support.wafers import get_tracking, get_wafer

NOW = datetime(2026, 10, 15, 9, 0)


@pytest.fixture()
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setattr(tracking_source._DEMO, "_now", lambda: NOW)


def test_raw_lot_values_are_grouped_by_lot_name():
    df = pd.DataFrame(
        [
            {"jira_nom_lots": "QMDE 06", "n_fdl": 2, "first_created": "2026-01-02", "last_created": "2026-02-01"},
            {"jira_nom_lots": "qmde06, QT12", "n_fdl": 1, "first_created": "2026-03-01", "last_created": "2026-03-01"},
            {"jira_nom_lots": "To be updated", "n_fdl": 9, "first_created": None, "last_created": None},
        ]
    )
    lots = {lot["name"]: lot for lot in jira.group_lots(df)}
    assert set(lots) == {"QMDE06", "QT12"}
    assert lots["QMDE06"] == {"name": "QMDE06", "raw": ["QMDE 06", "qmde06, QT12"], "n_fdl": 3, "first": "2026-01-02", "last": "2026-03-01"}


def test_the_wafers_of_a_lot_are_read_once_in_order():
    df = pd.DataFrame(
        [
            {"jira_nom_lots": "QMDE 06", "Request_Number": "FDL-1", "wafer": "A1"},
            {"jira_nom_lots": "QMDE 06", "Request_Number": "FDL-2", "wafer": "a1"},
            {"jira_nom_lots": "QMDE 06, QT12", "Request_Number": "FDL-3", "wafer": "B2"},
        ]
    )
    assert jira.lot_wafers(df, "QMDE06") == [{"lasermark": "A1", "fdl": "FDL-1"}, {"lasermark": "B2", "fdl": "FDL-3"}]


def test_jira_lots_are_listed_and_imported_with_their_wafers_and_records(client, demo):
    signup(client, "lots@example.com")
    listed = client.get("/api/jira-lots", params={"q": "qmde 03"}).json()
    assert [lot["name"] for lot in listed["items"]] == ["QMDE03"] and listed["items"][0]["spectre"] is None
    response = client.post("/api/jira-lots/import", json={"name": "qmde03"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] and result["added"] == result["wafers"] == result["records_created"] > 0
    lot = client.get("/api/lots", params={"code": "QMDE03"}).json()[0]
    assert lot["source"] == "prism" and len(lot["wafers"]) == result["wafers"]
    first = lot["wafers"][0]["lasermark"]
    assert get_wafer(client, first)["record"]["lasermark"] == first
    again = client.post("/api/jira-lots/import", json={"name": "QMDE03"}).json()  # rien de neuf
    assert not again["created"] and again["added"] == 0 and again["records_created"] == 0
    assert client.get("/api/jira-lots", params={"q": "QMDE03"}).json()["items"][0]["spectre"]["wafers"] == result["wafers"]
    assert client.post("/api/jira-lots/import", json={"name": "NOPE99"}).status_code == 404


def test_reading_a_plate_online_makes_its_jira_lot_exist(client, demo):
    signup(client, "detect@example.com")
    fiche = get_tracking(client, "T001").json()
    assert fiche["lot_source"] == "JIRA"
    lots = client.get("/api/lots", params={"wafer": "T001", "view": "summary"}).json()
    assert [lot["code"] for lot in lots] == [fiche["lot_name"]] and lots[0]["source"] == "prism"
    get_tracking(client, "T002")
    assert client.get("/api/lots", params={"code": fiche["lot_name"]}).json()  # toujours un seul lot de ce nom


# --- clôture automatique d'un lot arrêté ----------------------------------------------------------


def _moves(monkeypatch, moves):
    from spectre.plugins.lots import auto_close

    monkeypatch.setattr(auto_close.tracking, "last_movements", lambda keys: {k: v for k, v in moves.items() if k in set(keys)})


def test_a_lot_whose_plates_all_stopped_a_week_ago_closes_and_reopens_when_one_moves(client, monkeypatch):
    from spectre.plugins.lots import auto_close

    signup(client, "stop@example.com")
    lot = client.post("/api/lots", json={"code": "STOP1", "started_on": "2026-09-01", "wafers": ["A1", "A2"]}).json()
    now = datetime(2026, 10, 15, 9, 0)
    _moves(monkeypatch, {"A1": "2026-10-01 10:00"})  # A2 jamais lue : arrêt inconnu, le lot reste
    assert auto_close.sweep(now=now) == []
    _moves(monkeypatch, {"A1": "2026-10-01 10:00", "A2": "2026-10-10 14:30"})  # A2 a bougé il y a 5 jours
    assert auto_close.sweep(now=now) == []
    assert auto_close.sweep(now=datetime(2026, 10, 17, 15, 0)) == [lot["id"]]  # une semaine sans rien
    closed = client.get(f"/api/lots/{lot['id']}").json()
    assert (closed["status"], closed["exited_on"], closed["stopped_since"]) == ("done", "2026-10-10", "2026-10-10 14:30")
    _moves(monkeypatch, {"A1": "2026-10-20 08:00", "A2": "2026-10-10 14:30"})  # A1 repart
    assert auto_close.sweep(now=datetime(2026, 10, 20, 9, 0)) == [lot["id"]]
    reopened = client.get(f"/api/lots/{lot['id']}").json()
    assert (reopened["status"], reopened["exited_on"], reopened["stopped_since"]) == ("wip", None, None)


def test_a_lot_reopened_by_hand_is_not_closed_again_and_a_planned_one_waits(client, monkeypatch):
    from spectre.plugins.lots import auto_close

    signup(client, "manual@example.com")
    planned = client.post("/api/lots", json={"code": "PLAN1", "wafers": ["B1"]}).json()  # déclaratif, pas commencé
    started = client.post("/api/lots", json={"code": "RUN1", "started_on": "2026-09-01", "wafers": ["B2"]}).json()
    _moves(monkeypatch, {"B1": "2026-09-01 10:00", "B2": "2026-09-01 10:00"})
    assert auto_close.sweep(now=datetime(2026, 10, 15)) == [started["id"]]
    response = client.get(f"/api/lots/{started['id']}")
    reopen = client.patch(f"/api/lots/{started['id']}", json={"status": "wip"}, headers={"If-Match": response.headers["ETag"]})
    assert reopen.status_code == 200 and reopen.json()["status"] == "wip"
    assert auto_close.sweep(now=datetime(2026, 10, 30)) == []  # décidé à la main après le dernier mouvement
    assert client.get(f"/api/lots/{planned['id']}").json()["status"] == "planned"


# --- clôture d'un lot dont toutes les FDL sont closes ----------------------------------------------


def test_the_state_of_the_plate_fdls_follows_their_ticket_or_their_steps():
    from spectre.plugins.wafers import tracking_model

    rec = {
        "tickets": [
            {"request": "FDL-0012", "via": "wafer", "closed": "2026-10-02 10:00"},
            {"request": "FDL-13", "via": "wafer", "closed": None},
        ],
        "epitaxy": [{"request": "FDL-20"}, {"request": "FDL-21"}, {"request": "FDL-22"}],
        "fdls": {
            "FDL-13": {"n": 2, "n_done": 2, "n_todo": 0, "n_running": 0, "n_hold": 0, "last_done": {"closed": "2026-10-05 08:00"}},  # son ticket l'emporte : ouverte
            "FDL-20": {"n": 3, "n_done": 2, "n_skipped": 1, "n_todo": 0, "n_running": 0, "n_hold": 0, "last_done": {"closed": "2026-10-04 09:30"}},
            "FDL-21": {"n": 2, "n_done": 1, "n_todo": 1, "n_running": 0, "n_hold": 0, "last_done": None},
        },
    }
    assert tracking_model.fdl_closures(rec) == {
        "FDL-12": {"closed": True, "at": "2026-10-02 10:00"},
        "FDL-13": {"closed": False, "at": None},
        "FDL-20": {"closed": True, "at": "2026-10-04 09:30"},
        "FDL-21": {"closed": False, "at": None},
        "FDL-22": {"closed": False, "at": None},  # rien d'autre que son numéro : le doute garde le lot ouvert
    }


def _keep(lasermark, closures):
    from datetime import timezone

    from spectre.plugins.wafers import tracking
    from spectre.plugins.wafers.service import wafer_key

    tracking._save(wafer_key(lasermark), lasermark, "demo", {"fdl_closures": closures, "last_movement": "2026-10-14 08:00"}, datetime(2026, 10, 15, tzinfo=timezone.utc), None)


def test_a_lot_whose_fdls_are_all_closed_is_finished_and_reopens_when_one_opens(client, monkeypatch):
    from spectre.plugins.lots import auto_close

    signup(client, "fdlclose@example.com")
    lot = client.post("/api/lots", json={"code": "FDLC1", "started_on": "2026-09-01", "wafers": ["C1", "C2"]}).json()
    now = datetime(2026, 10, 15, 9, 0)
    _moves(monkeypatch, {"C1": "2026-10-14 08:00", "C2": "2026-10-14 08:00"})  # rien n'est à l'arrêt : seule la règle des FDL joue
    closed = {"closed": True, "at": "2026-10-12 16:00"}
    _keep("C1", {"FDL-1": closed, "FDL-2": {"closed": True, "at": "2026-10-09 10:00"}})
    assert auto_close.sweep(now=now) == []  # C2 jamais lue en ligne : ses FDL sont inconnues
    _keep("C2", {"FDL-3": {"closed": False, "at": None}})
    assert auto_close.sweep(now=now) == []  # une FDL ouverte
    _keep("C2", {"FDL-3": closed})
    assert auto_close.sweep(now=now) == [lot["id"]]
    done = client.get(f"/api/lots/{lot['id']}").json()
    assert (done["status"], done["exited_on"], done["stopped_since"], done["stopped_reason"]) == ("done", "2026-10-12", "2026-10-12 16:00", "fdl")
    assert auto_close.sweep(now=datetime(2026, 11, 30)) == []  # stable
    _keep("C2", {"FDL-3": closed, "FDL-4": {"closed": False, "at": None}})  # une nouvelle FDL s'ouvre
    assert auto_close.sweep(now=now) == [lot["id"]]
    reopened = client.get(f"/api/lots/{lot['id']}").json()
    assert (reopened["status"], reopened["exited_on"], reopened["stopped_since"], reopened["stopped_reason"]) == ("wip", None, None, None)


def test_a_plate_without_any_fdl_does_not_finish_the_lot_alone(client, monkeypatch):
    from spectre.plugins.lots import auto_close

    signup(client, "nofdl@example.com")
    lot = client.post("/api/lots", json={"code": "FDLC2", "started_on": "2026-09-01", "wafers": ["D1"]}).json()
    _moves(monkeypatch, {"D1": "2026-10-14 08:00"})
    _keep("D1", {})
    assert auto_close.sweep(now=datetime(2026, 10, 15, 9, 0)) == []
    assert client.get(f"/api/lots/{lot['id']}").json()["status"] == "wip"


def test_refreshing_all_the_wafers_of_a_lot_reads_them_again_and_applies_the_rules(client, demo):
    signup(client, "refresh@example.com")
    get_tracking(client, "T001"), get_tracking(client, "T002")  # lues une première fois
    lot = client.post("/api/lots", json={"code": "REFR1", "wafers": ["T001", "T002"]}).json()
    response = client.post(f"/api/lots/{lot['id']}/refresh")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["refreshed"] == 2 and result["failed"] == []
    assert get_tracking(client, "T001").json()["meta"]["age_hours"] == 0  # relue à l'instant
    assert client.post("/api/lots/99999/refresh").status_code == 404
