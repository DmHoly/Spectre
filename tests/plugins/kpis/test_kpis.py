from __future__ import annotations

import logging

from support.accounts import signup
from support.experiments import launch
from support.http import assert_handler_404
from support.microprojects import create_microproject


def test_trend_kpis_are_listed_and_served_lazily(client):
    signup(client, "boss@example.com")
    kpis = client.get("/api/areas/native-pt2/kpis").json()
    by_key = {k["key"]: k for k in kpis}
    assert list(by_key) == ["activite", "eqe", "pl", "defauts", "rendement"]
    assert by_key["activite"]["status"] == "live"
    assert by_key["eqe"]["status"] == "placeholder" and by_key["pl"]["status"] == "placeholder"  # sans données de démo
    assert [v["key"] for v in by_key["activite"]["variants"]] == ["running", "wafers"]

    live = client.get("/api/areas/native-pt2/kpis/activite?months=6").json()
    assert live["status"] == "live" and len(live["points"]) == 6 and len(live["periods"]) == 6
    assert live["variant"] == "running" and live["unit"] == "expériences"
    assert all(p["value"] == 0 for p in live["points"])

    placeholder = client.get("/api/areas/native-pt2/kpis/pl").json()
    assert placeholder["status"] == "placeholder" and placeholder["points"] == [] and len(placeholder["periods"]) == 12

    assert_handler_404(client.get("/api/areas/native-pt2/kpis/inconnu"), "inconnu")
    assert_handler_404(client.get("/api/areas/inconnu/kpis"))
    assert_handler_404(client.get("/api/areas/inconnu/kpis/activite"))
    assert client.get("/api/areas/native-pt2/kpis/activite?months=0").status_code == 422


def test_month_periods_cross_the_year_boundary():
    from datetime import date

    from spectre.plugins.kpis.service import month_periods

    assert month_periods(3, today=date(2027, 2, 10)) == ["2026-12", "2027-01", "2027-02"]


def test_activity_trend_counts_experiments_in_progress_and_their_wafers(client):
    signup(client, "boss@example.com")
    microproject = create_microproject(client, "Suivi activite", management_area_slug="native-pt2")
    for title, wafers in (("Essai A", ["W1", "W2"]), ("Essai B", ["W3"])):
        launch(client, microproject["slug"], title=title, intent="x", entities=[{"sample_id": w} for w in wafers])

    running = client.get("/api/areas/native-pt2/kpis/activite?months=3").json()
    assert [p["value"] for p in running["points"]][-1] == 2  # two studies in progress this month
    wafers = client.get("/api/areas/native-pt2/kpis/activite?months=3&variant=wafers").json()
    assert wafers["variant"] == "wafers" and wafers["unit"] == "wafers"
    assert [p["value"] for p in wafers["points"]][-1] == 3

    unknown = client.get("/api/areas/native-pt2/kpis/activite?variant=inconnue")
    assert unknown.status_code == 422 and "inconnue" in unknown.json()["detail"]
    assert client.get("/api/areas/native-pt2/kpis/pl?variant=x").status_code == 422  # un KPI sans variante


def test_a_wafer_followed_by_two_studies_is_engaged_once(client):
    signup(client, "boss@example.com")
    microproject = create_microproject(client, "Suivi wafers", management_area_slug="native-pt2")
    launch(client, microproject["slug"], title="Essai A", intent="x", entities=[{"sample_id": "W12-A3"}, {"sample_id": "W1"}])
    launch(client, microproject["slug"], title="Essai B", intent="x", entities=[{"sample_id": "w12 a3"}])

    wafers = client.get("/api/areas/native-pt2/kpis/activite?months=1&variant=wafers").json()
    assert [p["value"] for p in wafers["points"]] == [2]


def test_a_failing_kpi_says_so_without_leaking_the_error(client, monkeypatch, caplog):
    from dataclasses import replace

    from spectre.plugins.kpis import service as trends

    def broken(area, months, variant):
        raise RuntimeError("C:/secret/chemin/base.db verrouillée")

    signup(client, "boss@example.com")
    monkeypatch.setitem(trends._REGISTRY, "activite", [replace(trends.get_kpi("activite"), provider=broken)])

    with caplog.at_level(logging.ERROR, logger="spectre.plugins.kpis.service"):
        failed = client.get("/api/areas/native-pt2/kpis/activite").json()
    assert failed["status"] == "error" and failed["points"] == []
    assert "secret" not in failed["message"] and "journalisée" in failed["message"]
    assert "base.db verrouillée" in caplog.text  # la trace complète est dans le journal du serveur


def test_activity_counts_a_study_in_every_month_it_was_in_progress():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from spectre.plugins.kpis.service import _running_intervals

    def version(day, status):
        return SimpleNamespace(created_at=datetime(2026, *day, tzinfo=timezone.utc), conclusion=SimpleNamespace(status=status))

    # lancée fin janvier, conclue début mars, rouverte en mai (évolution) et toujours en cours
    versions = [version((1, 28), "draft"), version((2, 10), "running"), version((3, 2), "concluded"), version((5, 5), "draft")]
    intervals = _running_intervals(versions)
    assert intervals == [(versions[0].created_at, versions[2].created_at), (versions[3].created_at, None)]
