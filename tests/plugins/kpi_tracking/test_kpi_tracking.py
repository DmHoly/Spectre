"""Le plugin kpi_tracking : les KPI qu'un µprojet suit (colonnes de KPI de PRISM) et leurs boîtes à
moustaches par plaque. La source est la démo (``SPECTRE_DEMO_DATA=1``) : aucun accès base."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import UpstreamError
from spectre.plugins.kpi_tracking.service import box_stats
from support.accounts import login, signup
from support.experiments import launch
from support.http import assert_handler_404
from support.microprojects import add_member, create_microproject

BASE = "/api/microprojects/{}/kpi-tracking"


@pytest.fixture(autouse=True)
def demo_source(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def track(client, slug, hook, column, **fields):
    return client.post(f"{BASE.format(slug)}/kpis", json={"hook": hook, "column": column, **fields})


def test_the_catalog_offers_kpi_columns_of_per_wafer_types_only(client):
    signup(client, "boss@example.com")
    microproject = create_microproject(client, "Suivi KPI")
    catalog = client.get(f"{BASE.format(microproject['slug'])}/catalog").json()
    keys = {k["key"] for k in catalog}
    assert {"eqe:max_EQE", "pl:Integrated PL (a.u.)"} <= keys
    assert "eqe:V at Max EQE" in keys and "eqe:I at Max EQE" in keys  # « A / B » : deux KPI
    assert not [k for k in catalog if k["column"].lower() in ("wafername", "x", "y")]  # ni identifiant ni position
    assert not [k for k in catalog if k["hook"] in ("waferlist", "fdl_wafers")]  # pas un type par plaque


def test_choose_rename_and_drop_tracked_kpis(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI")["slug"]
    assert client.get(f"{BASE.format(slug)}/kpis").json() == []

    created = track(client, slug, "eqe", "max_EQE", label="  EQE   max ")
    assert created.status_code == 201 and created.headers["Location"].endswith(f"/kpis/{created.json()['id']}")
    kpi = created.json()
    assert kpi["title"] == "EQE max" and kpi["hook_title"] and kpi["available"] is True

    assert track(client, slug, "eqe", "max_EQE").status_code == 409  # une seule fois
    unknown = track(client, slug, "eqe", "n_existe_pas")
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_kpi"
    assert track(client, slug, "eqe", "wafername").status_code == 422  # un identifiant n'est pas un KPI
    assert track(client, slug, "pl", "Integrated PL (a.u.)", label="x" * 81).status_code == 422

    renamed = client.patch(f"{BASE.format(slug)}/kpis/{kpi['id']}", json={"label": ""})
    assert renamed.status_code == 200 and renamed.json()["title"] == "max_EQE"

    track(client, slug, "pl", "Integrated PL (a.u.)")
    assert [k["column"] for k in client.get(f"{BASE.format(slug)}/kpis").json()] == ["max_EQE", "Integrated PL (a.u.)"]

    assert client.delete(f"{BASE.format(slug)}/kpis/{kpi['id']}").status_code == 204
    assert [k["column"] for k in client.get(f"{BASE.format(slug)}/kpis").json()] == ["Integrated PL (a.u.)"]
    assert_handler_404(client.delete(f"{BASE.format(slug)}/kpis/{kpi['id']}"))
    assert_handler_404(client.patch(f"{BASE.format(slug)}/kpis/9999", json={"label": "x"}))


def test_a_kpi_belongs_to_its_microproject(client):
    signup(client, "boss@example.com")
    first = create_microproject(client, "Premier")["slug"]
    second = create_microproject(client, "Second")["slug"]
    kpi = track(client, first, "eqe", "max_EQE").json()
    assert client.get(f"{BASE.format(second)}/kpis").json() == []
    assert_handler_404(client.delete(f"{BASE.format(second)}/kpis/{kpi['id']}"))
    assert len(client.get(f"{BASE.format(first)}/kpis").json()) == 1


def test_distributions_draw_one_box_per_tracked_wafer(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI")["slug"]
    launch(client, slug, title="Essai A", intent="x", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    launch(client, slug, title="Essai B", intent="x", entities=[{"sample_id": "w1"}, {"sample_id": "W3"}])  # W1 suivie deux fois
    track(client, slug, "eqe", "max_EQE")
    track(client, slug, "pl", "Integrated PL (a.u.)")
    track(client, slug, "eqe", "I at Max EQE")  # une colonne que la requête (démo) ne renvoie pas

    result = client.get(f"{BASE.format(slug)}/distributions").json()
    assert result["source"] == "demo"
    assert sorted(w["wafer"].upper() for w in result["wafers"]) == ["W1", "W2", "W3"]
    by_column = {k["column"]: k for k in result["kpis"]}

    eqe = by_column["max_EQE"]
    assert eqe["status"] == "ok" and len(eqe["groups"]) == 3
    for group in eqe["groups"]:
        stats = group["stats"]
        assert stats["n"] > 50
        assert stats["minimum"] <= stats["whisker_low"] <= stats["q1"] <= stats["median"] <= stats["q3"] <= stats["whisker_high"] <= stats["maximum"]
    first = next(g for g in eqe["groups"] if g["wafer"].upper() == "W1")
    assert sorted(s["title"] for s in first["studies"]) == ["Essai A", "Essai B"]
    assert by_column["Integrated PL (a.u.)"]["status"] == "ok"

    broken = by_column["I at Max EQE"]  # un KPI en échec n'ôte rien aux autres
    assert broken["status"] == "error" and "I at Max EQE" in broken["message"] and broken["groups"] == []


def test_distributions_without_wafers_or_kpis(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Vide")["slug"]
    assert client.get(f"{BASE.format(slug)}/distributions").json() == {"source": None, "wafers": [], "kpis": []}

    track(client, slug, "eqe", "max_EQE")
    result = client.get(f"{BASE.format(slug)}/distributions").json()
    assert result["wafers"] == [] and result["kpis"][0]["status"] == "ok" and result["kpis"][0]["groups"] == []


def test_a_failing_prism_query_is_reported_on_its_kpis(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization

    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI")["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    track(client, slug, "eqe", "max_EQE")
    track(client, slug, "pl", "Integrated PL (a.u.)")
    real = characterization.query

    def flaky(key, parameters, *, refresh=False):
        if key == "eqe":
            raise UpstreamError("la requête PRISM a échoué : base injoignable")
        return real(key, parameters, refresh=refresh)

    monkeypatch.setattr(characterization, "query", flaky)
    by_column = {k["column"]: k for k in client.get(f"{BASE.format(slug)}/distributions").json()["kpis"]}
    assert by_column["max_EQE"]["status"] == "error" and "injoignable" in by_column["max_EQE"]["message"]
    assert by_column["Integrated PL (a.u.)"]["status"] == "ok"


def test_a_viewer_reads_but_cannot_choose_nor_refresh(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI")["slug"]
    track(client, slug, "eqe", "max_EQE")
    signup(client, "viewer@example.com")
    login(client, "boss@example.com")
    add_member(client, slug, "viewer@example.com", "viewer")
    login(client, "viewer@example.com")

    assert client.get(f"{BASE.format(slug)}/kpis").status_code == 200
    assert client.get(f"{BASE.format(slug)}/distributions").status_code == 200
    assert client.get(f"{BASE.format(slug)}/distributions?refresh=true").status_code == 403
    assert track(client, slug, "pl", "Integrated PL (a.u.)").status_code == 403


def test_box_stats():
    assert box_stats([]) is None
    stats, outliers = box_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
    assert (stats.n, stats.minimum, stats.maximum, stats.median) == (10, 1, 100, 5.5)
    assert (stats.q1, stats.q3) == (3.25, 7.75)
    assert outliers == [100] and stats.whisker_high == 9 and stats.whisker_low == 1
    single, none = box_stats([4.0])
    assert single.q1 == single.median == single.q3 == 4.0 and none == []
