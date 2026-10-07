"""Les plaques d'une FDL (spectre.plugins.wafers.fdl_source) : lues dans la source courante - la base
locale, saisie à la main, ou la démo (``SPECTRE_DEMO_DATA=1``), PRISM plus tard - pour associer chaque
place d'une étude à une vraie plaque."""

from __future__ import annotations

from support.accounts import signup
from support.wafers import get_fdl, put_fdl_wafers


def test_an_unknown_fdl_is_editable_in_the_local_base(client):
    signup(client, "fdl-local@example.com")
    fdl = get_fdl(client, "1234")
    assert fdl == {"fdl": "FDL-1234", "source": "local", "editable": True, "known": False, "wafers": []}


def test_the_wafers_of_an_fdl_are_entered_by_hand_once_each_in_order(client):
    signup(client, "fdl-write@example.com")
    response = put_fdl_wafers(client, "fdl 77", ["W3", " w-3 ", "W1", "", "W2"])
    assert response.status_code == 200
    assert response.json()["known"] is True
    assert response.json()["wafers"] == [{"lasermark": "W3", "slot": 1}, {"lasermark": "W1", "slot": 2}, {"lasermark": "W2", "slot": 3}]
    assert get_fdl(client, "FDL-77")["wafers"][0]["lasermark"] == "W3"
    # une nouvelle saisie remplace la précédente ; vide, la FDL redevient inconnue
    assert [w["lasermark"] for w in put_fdl_wafers(client, "77", ["W9"]).json()["wafers"]] == ["W9"]
    assert put_fdl_wafers(client, "77", []).json()["known"] is False


def test_the_demo_source_invents_the_same_wafers_for_the_same_fdl_and_is_read_only(client, monkeypatch):
    signup(client, "fdl-demo@example.com")
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    first = get_fdl(client, "FDL-42")
    assert first["source"] == "demo" and first["known"] and not first["editable"]
    assert 4 <= len(first["wafers"]) <= 12
    assert all(w["lasermark"].startswith("D42-W") for w in first["wafers"])
    assert get_fdl(client, "42") == first
    assert get_fdl(client, "ABC-3")["known"] is False
    refused = put_fdl_wafers(client, "42", ["W1"])
    assert refused.status_code == 409 and refused.json()["code"] == "fdl_source_read_only"


def test_reading_an_fdl_requires_a_session(client):
    assert client.get("/api/fdls/FDL-1").status_code == 401
