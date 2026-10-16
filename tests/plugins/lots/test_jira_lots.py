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
