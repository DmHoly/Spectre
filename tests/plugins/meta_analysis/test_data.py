"""Les données d'une analyse face à la référence : les KPI comparés (vérifiés au catalogue PRISM), une boîte par
plaque dans l'ordre de l'analyse et l'écart de chaque médiane à celle de la référence ; ce qu'on propose de
comparer - le catalogue, et d'abord les KPI que suivent les projets des plaques. La source est la démo
(``SPECTRE_DEMO_DATA=1``) : aucun accès base."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import UpstreamError
from support.accounts import signup
from support.experiments import launch
from support.http import assert_ok
from support.meta_analysis import create_analysis, update_analysis
from support.microprojects import create_microproject

AREA = "native-pt2"


@pytest.fixture(autouse=True)
def demo_source(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def kpis_of(client, analysis_id: int) -> dict:
    return assert_ok(client.get(f"/api/analyses/{analysis_id}/kpis"))


def test_the_compared_kpis_are_checked_against_the_catalog(client):
    signup(client, "analyse-kpi@example.com")
    analysis = create_analysis(client, "KPI", ["W1", "W2"])
    eqe = {"hook": "eqe", "column": "max_EQE"}

    saved = assert_ok(update_analysis(client, analysis["id"], kpis=[{**eqe, "label": "  EQE   max ", "better": "high"}, eqe, {"hook": "pl", "column": "Integrated PL (a.u.)"}]))
    assert [(k["column"], k["title"], k["better"]) for k in saved["kpis"]] == [("max_EQE", "EQE max", "high"), ("Integrated PL (a.u.)", "Integrated PL (a.u.)", None)]
    assert len(saved["kpis"]) == 2  # le même KPI aux mêmes filtres n'entre qu'une fois

    unknown = update_analysis(client, analysis["id"], kpis=[{"hook": "eqe", "column": "n_existe_pas"}])
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_kpi"
    bad_filter = update_analysis(client, analysis["id"], kpis=[{**eqe, "filters": [{"column": "inconnue", "op": "eq", "value": "x"}]}])
    assert bad_filter.status_code == 422 and bad_filter.json()["code"] == "unknown_filter_column"
    assert update_analysis(client, analysis["id"], kpis=[eqe] * 13).status_code == 422
    assert assert_ok(update_analysis(client, analysis["id"], kpis=[]))["kpis"] == []


def test_one_box_per_wafer_in_the_analysis_order_and_the_gap_to_the_reference(client):
    signup(client, "analyse-boites@example.com")
    analysis = create_analysis(client, "Boîtes", ["W2", "W1", "W3"])
    update_analysis(client, analysis["id"], kpis=[{"hook": "eqe", "column": "max_EQE"}, {"hook": "eqe", "column": "I at Max EQE"}])

    result = kpis_of(client, analysis["id"])
    assert result["source"] == "demo"
    eqe, missing = result["kpis"]
    assert eqe["status"] == "ok" and eqe["hook_title"]
    assert [g["wafer"] for g in eqe["groups"]] == ["W2", "W1", "W3"]  # la référence d'abord
    reference = eqe["groups"][0]
    assert reference["delta"] is None and reference["stats"]["n"] > 50
    for group in eqe["groups"][1:]:
        gap = group["stats"]["median"] - reference["stats"]["median"]
        assert group["delta"]["absolute"] == pytest.approx(gap)
        assert group["delta"]["relative"] == pytest.approx(gap / abs(reference["stats"]["median"]))
    # une colonne que la requête (démo) ne renvoie pas : le KPI le dit, les autres restent calculés
    assert missing["status"] == "error" and "I at Max EQE" in missing["message"]


def test_a_failing_prism_query_is_reported_on_its_kpis_only(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization

    signup(client, "analyse-panne@example.com")
    analysis = create_analysis(client, "Panne", ["W1", "W2"])
    update_analysis(client, analysis["id"], kpis=[{"hook": "eqe", "column": "max_EQE"}, {"hook": "pl", "column": "Integrated PL (a.u.)"}])
    real = characterization.query

    def flaky(key, parameters, *, refresh=False):
        if key == "eqe":
            raise UpstreamError("la requête PRISM a échoué : base injoignable")
        return real(key, parameters, refresh=refresh)

    monkeypatch.setattr(characterization, "query", flaky)
    eqe, pl = kpis_of(client, analysis["id"])["kpis"]
    assert eqe["status"] == "error" and "injoignable" in eqe["message"] and eqe["groups"] == []
    assert pl["status"] == "ok" and all(g["stats"] for g in pl["groups"])


def test_the_kpis_tracked_by_the_wafers_projects_are_suggested_first(client):
    signup(client, "analyse-choix@example.com")
    slug = create_microproject(client, "Suivi", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    tracked = client.post(f"/api/areas/{AREA}/kpi-tracking/kpis", json={"hook": "eqe", "column": "max_EQE", "goal": {"mode": "max"}})
    assert tracked.status_code == 201
    client.post(f"/api/areas/{AREA}/kpi-tracking/kpis", json={"hook": "pl", "column": "Integrated PL (a.u.)"})
    analysis = create_analysis(client, "Choix", ["W1", "W9"])

    choices = assert_ok(client.get(f"/api/analyses/{analysis['id']}/kpi-choices"))
    assert {"eqe:max_EQE", "pl:Integrated PL (a.u.)"} <= {k["key"] for k in choices["catalog"]}
    assert [(s["column"], s["better"], s["area"]["slug"]) for s in choices["suggested"]] == [("max_EQE", "high", AREA), ("Integrated PL (a.u.)", None, AREA)]

    update_analysis(client, analysis["id"], kpis=[{"hook": "eqe", "column": "max_EQE"}])
    left = assert_ok(client.get(f"/api/analyses/{analysis['id']}/kpi-choices"))["suggested"]
    assert [s["column"] for s in left] == ["Integrated PL (a.u.)"]  # déjà comparé : plus proposé
