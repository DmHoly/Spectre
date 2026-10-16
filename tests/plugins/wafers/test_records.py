"""Les fiches de plaque (spectre.plugins.wafers.records) : chercher des plaques - plusieurs à la
fois - dans Spectre puis dans les bases de la ligne, créer la fiche de celles que la base connaît
(ou pas : une plaque d'avant toute base), les retrouver dans l'index, la recherche et leur page sans
qu'aucune étude ne les suive, et les retirer. Aucun test ne touche à une base : la démo répond, et
PRISM est remplacé par un enregistreur d'appels."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from spectre.plugins.wafers import tracking_model, tracking_source
from spectre.plugins.wafers.tracking_model import LookupFrames, lookup_summaries
from spectre.plugins.wafers.tracking_source import PrismSource

from support.accounts import signup, switch_user
from support.experiments import launch
from support.microprojects import signup_with_microproject
from support.search import search
from support.wafers import create_records, delete_record, get_wafer, list_wafers, lookup_wafers

NOW = datetime(2026, 10, 15, 9, 0)


@pytest.fixture()
def demo(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    monkeypatch.setattr(tracking_source._DEMO, "_now", lambda: NOW)


# --- le résumé, depuis les tables --------------------------------------------------------------


def test_the_summary_reads_gozer_and_the_last_mes_step_of_each_wafer():
    record = pd.DataFrame([{"Wafer_Name": "WA1", "Substrat_Lasermark": "w12-a3", "Substrat_Type": "Si<111>", "Diameter_mm": 200, "Creation_Date": "2025-03-01 10:00"}])
    mes = pd.DataFrame(
        [
            {"physical_item_id": "W12A3", "physical_item_id_out": "W12A3", "physical_lot_id": "E1", "physical_lot_id_out": "E1", "productname": "uLED", "step_detailed_name": "Litho", "last_update": "2025-04-02 08:00"},
            {"physical_item_id": "W12A3", "physical_item_id_out": "W12A3", "physical_lot_id": "E1", "physical_lot_id_out": "E2", "productname": "uLED", "step_detailed_name": "Gravure", "last_update": "2025-04-03 08:00"},
            {"physical_item_id": "OTHER", "physical_item_id_out": "OTHER", "physical_lot_id": "E9", "physical_lot_id_out": "E9", "productname": "x", "step_detailed_name": "x", "last_update": "2025-04-09 08:00"},
        ]
    )
    out = lookup_summaries(LookupFrames(record=record, mes=mes), ["W12 A3", "other", "nowhere"])
    assert out["W12A3"] == {
        "gozer": True, "wafer_name": "WA1", "substrate": "Si<111>", "supplier": None, "diameter_mm": 200, "created": "2025-03-01 10:00",
        "mes": True, "lot": "E2", "product": "uLED", "last_step": "Gravure", "last_movement": "2025-04-03 08:00", "n_steps": 2,
    }
    assert out["OTHER"] == {"mes": True, "lot": "E9", "product": "x", "last_step": "x", "last_movement": "2025-04-09 08:00", "n_steps": 1}  # MES seule
    assert out["NOWHERE"] is None


def test_prism_is_asked_once_per_hook_for_all_the_wafers(monkeypatch):
    calls = []

    def run(hook, params):
        calls.append((hook, tuple(params["wafer_names"])))
        return pd.DataFrame([{"wafer_name": "WX", "substrat_lasermark": "A1"}]) if hook == "wafer_record" else pd.DataFrame()

    monkeypatch.setattr(PrismSource, "_run", staticmethod(run))
    out = PrismSource().lookup(["A1", "B2"])
    assert [hook for hook, _ in calls] == ["wafer_record", "wafer_epitaxy", "wafer_mes_history"]
    assert set(calls[0][1]) >= {"A1", "a1", "B2", "b2"}  # la MES garde la casse : on tente les variantes
    assert out == {"A1": {"gozer": True, "wafer_name": "WX", "substrate": None, "supplier": None, "diameter_mm": None, "created": None}, "B2": None}


def test_the_demo_knows_every_wafer_but_zz(demo):
    out = tracking_source.current_source().lookup(["T001", "ZZ-1"])
    assert out["T001"]["lot"].startswith("E26") and out["T001"]["wafer_name"] == "WT001" and out["ZZ1"] is None
    assert tracking_model.compact("T001") == "T001"


# --- chercher, créer, retrouver ----------------------------------------------------------------


def test_lookup_says_what_spectre_and_the_base_know_of_each_wafer(client, demo):
    slug = signup_with_microproject(client, "lookup@example.com", "Lots")
    launch(client, slug, title="Dopage", intent="x", entities=[{"sample_id": "W12-A3"}])
    found = lookup_wafers(client, ["w12 a3", "T001", "ZZ-9", "T001"])  # un doublon : une fois
    assert found["source"] == "demo" and found["base_error"] is None
    by = {item["key"]: item for item in found["items"]}
    assert list(by) == ["W12A3", "T001", "ZZ9"]
    assert by["W12A3"]["studies"] == 1 and by["W12A3"]["microprojects"][0]["slug"] == slug and by["W12A3"]["record"] is None
    assert by["W12A3"]["base"]["lot"] and by["T001"]["studies"] == 0 and by["T001"]["base"]["wafer_name"] == "WT001"
    assert by["ZZ9"]["base"] is None and by["ZZ9"]["studies"] == 0


def test_a_record_makes_a_wafer_exist_without_any_study(client, demo):
    signup(client, "records@example.com", name="Ada")
    created = create_records(client, ["T001", "ZZ-9"])
    assert [(r["key"], r["created"], r["source"]) for r in created["items"]] == [("T001", True, "demo"), ("ZZ9", True, "manual")]
    assert created["items"][0]["summary"]["lot"].startswith("E26") and created["items"][1]["summary"] == {}
    assert created["items"][0]["created_by"] == "Ada"
    again = create_records(client, ["t001"])
    assert again["items"][0]["created"] is False and again["items"][0]["lasermark"] == "T001"

    wafers = {w["key"]: w for w in list_wafers(client)}
    assert wafers["T001"]["count"] == 0 and wafers["T001"]["latest"] is None and wafers["T001"]["record"]["source"] == "demo"
    assert [w["key"] for w in list_wafers(client, q="T00")] == ["T001"]
    passport = get_wafer(client, "t001")
    assert passport["occurrences"] == [] and passport["record"]["summary"]["wafer_name"] == "WT001" and passport["lasermark"] == "T001"
    assert [hit["label"] for hit in search(client, "T001", types="wafer")] == ["T001"]  # la barre du haut aussi

    found = lookup_wafers(client, ["T001"])
    assert found["items"][0]["record"]["key"] == "T001"


def test_a_tracked_wafer_keeps_its_studies_and_shows_its_record(client, demo):
    slug = signup_with_microproject(client, "both@example.com", "Lots")
    launch(client, slug, title="Dopage", intent="x", entities=[{"sample_id": "W12-A3"}])
    create_records(client, ["W12A3"])
    wafer = list_wafers(client, q="W12A3")[0]
    assert wafer["count"] == 1 and wafer["lasermark"] == "W12-A3" and wafer["record"]["lasermark"] == "W12A3"
    assert get_wafer(client, "W12-A3")["record"]["source"] == "demo"
    # dans un µprojet (autocomplétion de la fiche) : ses plaques suivies seulement
    assert all(w["count"] for w in list_wafers(client, microproject=slug))


def test_several_lasermarks_are_searched_at_once(client):
    slug = signup_with_microproject(client, "multi@example.com", "Lots")
    for lm in ("W1", "W2", "W3"):
        launch(client, slug, title=lm, intent="x", entities=[{"sample_id": lm}])
    assert [w["key"] for w in list_wafers(client, q=["w1", "W3", ""])] == ["W1", "W3"]


def test_records_are_created_even_when_the_base_is_down(client, monkeypatch):
    signup(client, "down@example.com")

    def down(hook, params):
        raise RuntimeError("timeout")

    monkeypatch.setattr(PrismSource, "_run", staticmethod(down))
    found = lookup_wafers(client, ["W5"])
    assert found["base_error"] and found["items"][0]["base"] is None and found["items"][0]["studies"] == 0
    created = create_records(client, ["W5"])
    assert created["base_error"] and created["items"][0]["source"] == "manual"


def test_a_record_is_deleted_by_its_author_or_an_admin(client, demo):
    signup(client, "admin@example.com")  # le premier compte est administrateur
    switch_user(client, "author@example.com")
    create_records(client, ["T001", "T002"])
    switch_user(client, "stranger@example.com")
    assert delete_record(client, "T001").status_code == 403
    switch_user(client, "author@example.com")
    assert delete_record(client, "T001").status_code == 204
    assert delete_record(client, "T001").status_code == 404
    switch_user(client, "admin@example.com")
    assert delete_record(client, "t002").status_code == 204
    assert list_wafers(client) == []


def test_lookup_and_records_refuse_too_many_or_no_wafers(client):
    signup(client, "limits@example.com")
    assert client.get("/api/wafers/lookup").status_code == 422
    assert client.get("/api/wafers/lookup", params={"lasermark": [""]}).status_code == 200  # un vide : rien
    assert client.post("/api/wafer-records", json={"lasermarks": [" "]}).status_code == 422
    assert client.post("/api/wafer-records", json={"lasermarks": [f"W{n}" for n in range(101)]}).status_code == 422
