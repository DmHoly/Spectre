"""Le plugin kpi_tracking : les KPI qu'un projet corporate suit (colonnes de KPI de PRISM) et leurs boîtes à
moustaches par plaque, sur les plaques de tous ses µprojets. La source est la démo (``SPECTRE_DEMO_DATA=1``) :
aucun accès base."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import UpstreamError
from spectre.plugins.kpi_tracking.service import box_stats
from support.accounts import login, signup
from support.experiments import launch
from support.http import assert_handler_404
from support.microprojects import create_microproject

AREA = "native-pt2"
BASE = "/api/areas/{}/kpi-tracking"


@pytest.fixture(autouse=True)
def demo_source(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def track(client, slug, hook, column, **fields):
    return client.post(f"{BASE.format(slug)}/kpis", json={"hook": hook, "column": column, **fields})


def test_the_catalog_offers_kpi_columns_of_per_wafer_types_only(client):
    signup(client, "boss@example.com")
    catalog = client.get(f"{BASE.format(AREA)}/catalog").json()
    keys = {k["key"] for k in catalog}
    assert {"eqe:max_EQE", "pl:Integrated PL (a.u.)"} <= keys
    assert "eqe:V at Max EQE" in keys and "eqe:I at Max EQE" in keys  # « A / B » : deux KPI
    assert not [k for k in catalog if k["column"].lower() in ("wafername", "x", "y")]  # ni identifiant ni position
    assert not [k for k in catalog if k["hook"] in ("waferlist", "fdl_wafers")]  # pas un type par plaque
    assert_handler_404(client.get(f"{BASE.format('inconnu')}/catalog"))


def test_choose_rename_and_drop_tracked_kpis(client):
    signup(client, "boss@example.com")
    assert client.get(f"{BASE.format(AREA)}/kpis").json() == []

    created = track(client, AREA, "eqe", "max_EQE", label="  EQE   max ")
    assert created.status_code == 201 and created.headers["Location"].endswith(f"/kpis/{created.json()['id']}")
    kpi = created.json()
    assert kpi["title"] == "EQE max" and kpi["hook_title"] and kpi["available"] is True

    assert track(client, AREA, "eqe", "max_EQE").status_code == 409  # une seule fois
    unknown = track(client, AREA, "eqe", "n_existe_pas")
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_kpi"
    assert track(client, AREA, "eqe", "wafername").status_code == 422  # un identifiant n'est pas un KPI
    assert track(client, AREA, "pl", "Integrated PL (a.u.)", label="x" * 81).status_code == 422

    renamed = client.patch(f"{BASE.format(AREA)}/kpis/{kpi['id']}", json={"label": ""})
    assert renamed.status_code == 200 and renamed.json()["title"] == "max_EQE"

    track(client, AREA, "pl", "Integrated PL (a.u.)")
    assert [k["column"] for k in client.get(f"{BASE.format(AREA)}/kpis").json()] == ["max_EQE", "Integrated PL (a.u.)"]

    assert client.delete(f"{BASE.format(AREA)}/kpis/{kpi['id']}").status_code == 204
    assert [k["column"] for k in client.get(f"{BASE.format(AREA)}/kpis").json()] == ["Integrated PL (a.u.)"]
    assert_handler_404(client.delete(f"{BASE.format(AREA)}/kpis/{kpi['id']}"))
    assert_handler_404(client.patch(f"{BASE.format(AREA)}/kpis/9999", json={"label": "x"}))


def test_a_kpi_belongs_to_its_project(client):
    signup(client, "boss@example.com")
    other = client.post("/api/areas", json={"name": "Autre projet"}).json()["slug"]
    kpi = track(client, AREA, "eqe", "max_EQE").json()
    assert client.get(f"{BASE.format(other)}/kpis").json() == []
    assert_handler_404(client.delete(f"{BASE.format(other)}/kpis/{kpi['id']}"))
    assert len(client.get(f"{BASE.format(AREA)}/kpis").json()) == 1


def test_distributions_gather_the_wafers_of_every_microproject_of_the_project(client):
    signup(client, "boss@example.com")
    first = create_microproject(client, "Premier", area=AREA)["slug"]
    second = create_microproject(client, "Second", area=AREA)["slug"]
    elsewhere = create_microproject(client, "Ailleurs")["slug"]  # hors du projet : ses plaques ne comptent pas
    launch(client, first, title="Essai A", intent="x", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    launch(client, second, title="Essai B", intent="x", entities=[{"sample_id": "w1"}, {"sample_id": "W3"}])  # W1 suivie deux fois
    launch(client, elsewhere, title="Essai C", intent="x", entities=[{"sample_id": "W9"}])
    track(client, AREA, "eqe", "max_EQE")
    track(client, AREA, "pl", "Integrated PL (a.u.)")
    track(client, AREA, "eqe", "I at Max EQE")  # une colonne que la requête (démo) ne renvoie pas

    result = client.get(f"{BASE.format(AREA)}/distributions").json()
    assert result["source"] == "demo"
    assert sorted(w["wafer"].upper() for w in result["wafers"]) == ["W1", "W2", "W3"]
    by_column = {k["column"]: k for k in result["kpis"]}

    eqe = by_column["max_EQE"]
    assert eqe["status"] == "ok" and len(eqe["groups"]) == 3
    for group in eqe["groups"]:
        stats = group["stats"]
        assert stats["n"] > 50
        assert stats["minimum"] <= stats["whisker_low"] <= stats["q1"] <= stats["median"] <= stats["q3"] <= stats["whisker_high"] <= stats["maximum"]
    w1 = next(g for g in eqe["groups"] if g["wafer"].upper() == "W1")
    assert [m["slug"] for m in w1["microprojects"]] == [first, second]  # le plus ancien d'abord
    assert sorted(s["title"] for s in w1["studies"]) == ["Essai A", "Essai B"]
    assert by_column["Integrated PL (a.u.)"]["status"] == "ok"

    broken = by_column["I at Max EQE"]  # un KPI en échec n'ôte rien aux autres
    assert broken["status"] == "error" and "I at Max EQE" in broken["message"] and broken["groups"] == []


def test_distributions_without_wafers_or_kpis(client):
    signup(client, "boss@example.com")
    assert client.get(f"{BASE.format(AREA)}/distributions").json() == {"source": None, "wafers": [], "kpis": []}

    track(client, AREA, "eqe", "max_EQE")
    result = client.get(f"{BASE.format(AREA)}/distributions").json()
    assert result["wafers"] == [] and result["kpis"][0]["status"] == "ok" and result["kpis"][0]["groups"] == []


def test_a_failing_prism_query_is_reported_on_its_kpis(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization

    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    track(client, AREA, "eqe", "max_EQE")
    track(client, AREA, "pl", "Integrated PL (a.u.)")
    real = characterization.query

    def flaky(key, parameters, *, refresh=False):
        if key == "eqe":
            raise UpstreamError("la requête PRISM a échoué : base injoignable")
        return real(key, parameters, refresh=refresh)

    monkeypatch.setattr(characterization, "query", flaky)
    by_column = {k["column"]: k for k in client.get(f"{BASE.format(AREA)}/distributions").json()["kpis"]}
    assert by_column["max_EQE"]["status"] == "error" and "injoignable" in by_column["max_EQE"]["message"]
    assert by_column["Integrated PL (a.u.)"]["status"] == "ok"


def test_anyone_reads_but_only_a_manager_chooses_or_refreshes(client):
    signup(client, "boss@example.com")  # le premier compte est administrateur
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai secret", intent="x", entities=[{"sample_id": "W1"}])
    kpi = track(client, AREA, "eqe", "max_EQE").json()
    signup(client, "reader@example.com")
    login(client, "reader@example.com")

    assert client.get(f"{BASE.format(AREA)}/kpis").status_code == 200
    seen = client.get(f"{BASE.format(AREA)}/distributions").json()
    group = seen["kpis"][0]["groups"][0]
    assert group["stats"] and group["microprojects"][0]["slug"] == slug
    assert [s["title"] for s in group["studies"]] == [None]  # le titre d'une étude reste à ceux qui lisent son µprojet
    assert client.get(f"{BASE.format(AREA)}/distributions?refresh=true").status_code == 403
    assert track(client, AREA, "pl", "Integrated PL (a.u.)").status_code == 403
    assert client.patch(f"{BASE.format(AREA)}/kpis/{kpi['id']}", json={"label": "x"}).status_code == 403
    assert client.delete(f"{BASE.format(AREA)}/kpis/{kpi['id']}").status_code == 403


def test_box_stats():
    assert box_stats([]) is None
    stats, outliers = box_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
    assert (stats.n, stats.minimum, stats.maximum, stats.median) == (10, 1, 100, 5.5)
    assert (stats.q1, stats.q3) == (3.25, 7.75)
    assert outliers == [100] and stats.whisker_high == 9 and stats.whisker_low == 1
    single, none = box_stats([4.0])
    assert single.q1 == single.median == single.q3 == 4.0 and none == []


PL = "Integrated PL (a.u.)"


def distribution_of(client, column, title=None):
    kpis = [k for k in client.get(f"{BASE.format(AREA)}/distributions").json()["kpis"] if k["column"] == column and (title is None or k["title"] == title)]
    assert len(kpis) == 1, [k["title"] for k in kpis]
    return kpis[0]


def test_filters_keep_only_the_rows_that_match(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    plain = track(client, AREA, "pl", PL).json()
    centre = track(client, AREA, "pl", PL, filters=[{"column": "X", "op": "eq", "value": "0"}])  # la même colonne, filtrée
    assert centre.status_code == 201 and centre.json()["title"] == f"{PL} (X = 0)" and centre.json()["summary"] == "X = 0"
    nowhere = track(client, AREA, "pl", PL, filters=[{"column": "Dominant WL(nm)", "op": "gt", "value": 10000}]).json()

    total = distribution_of(client, PL, plain["title"])["groups"][0]["stats"]["n"]
    on_axis = distribution_of(client, PL, centre.json()["title"])["groups"][0]["stats"]["n"]
    assert 0 < on_axis < total
    assert distribution_of(client, PL, nowhere["title"])["groups"][0]["stats"] is None  # aucune ligne ne passe

    # plusieurs filtres se cumulent ; un nombre peut s'écrire avec une virgule
    both = track(
        client, AREA, "pl", PL, label="Axe, grandes longueurs",
        filters=[{"column": "X", "op": "eq", "value": "0"}, {"column": "Dominant WL(nm)", "op": "gte", "value": "0,5"}],
    ).json()
    assert distribution_of(client, PL, both["title"])["groups"][0]["stats"]["n"] == on_axis
    assert both["filters"][1] == {"column": "Dominant WL(nm)", "op": "gte", "value": 0.5}


def test_a_text_filter_picks_a_led(client):
    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    only = track(client, AREA, "eqe", "max_EQE", filters=[{"column": "Led_Name", "op": "contains", "value": "mono2-118x118-5805-r"}]).json()
    assert distribution_of(client, "max_EQE")["groups"][0]["stats"]["n"] == 1  # sans casse
    listed = track(client, AREA, "eqe", "max_EQE", filters=[{"column": "Led_Name", "op": "in", "value": "MONO2-118x118-5805-R; MONO2-118x118-5806-R"}]).json()
    assert listed["filters"][0]["value"] == ["MONO2-118x118-5805-R", "MONO2-118x118-5806-R"] and only["id"] != listed["id"]
    by_title = {k["title"]: k for k in client.get(f"{BASE.format(AREA)}/distributions").json()["kpis"]}
    assert by_title[listed["title"]]["groups"][0]["stats"]["n"] == 2
    is_lit = track(client, AREA, "eqe", "max_EQE", filters=[{"column": "is_lit", "op": "eq", "value": "oui"}]).json()
    unlit = track(client, AREA, "eqe", "max_EQE", filters=[{"column": "is_lit", "op": "ne", "value": "oui"}]).json()
    by_title = {k["title"]: k for k in client.get(f"{BASE.format(AREA)}/distributions").json()["kpis"]}
    lit, dead = (by_title[k["title"]]["groups"][0]["stats"] for k in (is_lit, unlit))
    assert lit["n"] > 50 and dead["n"] < lit["n"] and dead["maximum"] == 0  # les éteints : EQE nul


def test_filters_are_checked_and_editable(client):
    signup(client, "boss@example.com")
    kpi = track(client, AREA, "pl", PL).json()
    assert kpi["filters"] == [] and "Dominant WL(nm)" in kpi["filter_columns"] and "wafername" not in kpi["filter_columns"]

    def bad(filters, code=None, status=422):
        response = track(client, AREA, "pl", PL, filters=filters)
        assert response.status_code == status, response.text
        assert code is None or response.json()["code"] == code

    bad([{"column": "inconnue", "op": "eq", "value": "1"}], "unknown_filter_column")
    bad([{"column": "wafername", "op": "eq", "value": "W1"}], "unknown_filter_column")
    bad([{"column": "X", "op": "gt", "value": "beaucoup"}], "invalid_filter_value")
    bad([{"column": "X", "op": "contains", "value": "  "}], "invalid_filter_value")
    bad([{"column": "X", "op": "in", "value": " ; "}], "invalid_filter_value")
    bad([{"column": "X", "op": "environ", "value": "1"}])  # une comparaison inconnue : refusée par le schéma
    bad([{"column": "X", "op": "gt", "value": str(n)} for n in range(9)], "too_many_filters")
    assert track(client, AREA, "pl", PL).status_code == 409  # les mêmes filtres (aucun)

    url = f"{BASE.format(AREA)}/kpis/{kpi['id']}"
    edited = client.patch(url, json={"filters": [{"column": "Dominant WL(nm)", "op": "gt", "value": 613}]})
    assert edited.status_code == 200 and edited.json()["summary"] == "Dominant WL(nm) > 613" and edited.json()["title"] == f"{PL} (Dominant WL(nm) > 613)"
    assert client.patch(url, json={"label": "Rouge"}).json()["filters"][0]["value"] == 613  # une clé absente ne change rien
    twin = track(client, AREA, "pl", PL).json()
    assert client.patch(f"{BASE.format(AREA)}/kpis/{twin['id']}", json={"filters": [{"column": "Dominant WL(nm)", "op": "gt", "value": 613}]}).status_code == 409
    assert client.patch(url, json={"filters": []}).status_code == 409  # retirer ses filtres le ferait doublon de `twin`
    client.delete(f"{BASE.format(AREA)}/kpis/{twin['id']}")
    cleared = client.patch(url, json={"filters": [], "label": ""})
    assert cleared.status_code == 200 and cleared.json()["filters"] == [] and cleared.json()["title"] == PL


def test_a_wafer_measured_on_two_dates_gets_a_box_per_date(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization
    from spectre.plugins.characterization.source import QueryResult

    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    track(client, AREA, "ncel", "na_current_a")
    columns = ["wafername", "Test_Date", "na_current_a"]
    rows = [
        ["W1", "2026-09-01T08:00:00", 1.0], ["W1", "2026-09-01T09:30:00", 2.0], ["W1", "2026-09-20", 10.0], ["W1", "2026-09-20", 12.0],
        ["W2", "2026-09-05", 5.0],
    ]
    monkeypatch.setattr(characterization, "query", lambda key, parameters, *, refresh=False: QueryResult(source="prism", columns=columns, rows=rows))

    groups = distribution_of(client, "na_current_a")["groups"]
    # chronologique : l'ordre de l'axe du temps (W2 se place entre les deux mesures de W1)
    assert [(g["wafer"], g["date"], g["stats"]["n"], g["stats"]["median"]) for g in groups] == [
        ("W1", "2026-09-01", 2, 1.5), ("W2", "2026-09-05", 1, 5.0), ("W1", "2026-09-20", 2, 11.0),
    ]
    assert [(g["sort_date"], g["dated"]) for g in groups] == [("2026-09-01", True), ("2026-09-05", True), ("2026-09-20", True)]


def test_a_type_without_dates_is_placed_on_the_day_a_study_started_following_the_wafer(client):
    from datetime import date

    signup(client, "boss@example.com")
    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}])
    track(client, AREA, "eqe", "max_EQE")  # l'EQE n'a pas de colonne de date
    group = distribution_of(client, "max_EQE")["groups"][0]
    assert group["date"] is None and group["dated"] is False and group["sort_date"] == date.today().isoformat()


def test_the_distinct_values_of_a_column_are_offered_as_a_list(client):
    signup(client, "boss@example.com")
    url = f"{BASE.format(AREA)}/values"
    assert client.get(url, params={"hook": "pl", "column": "X"}).json()["kind"] == "empty"  # aucune plaque suivie

    slug = create_microproject(client, "Suivi KPI", area=AREA)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])

    leds = client.get(url, params={"hook": "eqe", "column": "Led_Name"}).json()
    assert leds["kind"] == "text" and leds["wafers"] == 2 and leds["source"] == "demo"
    assert leds["distinct"] == len(leds["values"]) > 100 and leds["values"][0]["count"] == 2  # chaque LED sur les deux plaques

    lit = client.get(url, params={"hook": "eqe", "column": "is_lit"}).json()
    assert lit["kind"] == "bool" and sorted(v["value"] for v in lit["values"]) == ["false", "true"]

    x = client.get(url, params={"hook": "pl", "column": "X"}).json()
    assert x["kind"] == "number" and x["minimum"] == -40 and x["maximum"] == 40
    assert [v["value"] for v in x["values"]] == sorted(v["value"] for v in x["values"])  # les nombres par valeur

    curve = client.get(url, params={"hook": "eqe", "column": "EQE"}).json()  # une courbe n'est pas une valeur
    assert curve["kind"] == "empty"

    assert client.get(url, params={"hook": "pl", "column": "inconnue"}).status_code == 422
    assert client.get(url, params={"hook": "pl", "column": "wafername"}).status_code == 422
    signup(client, "reader@example.com")
    login(client, "reader@example.com")
    assert client.get(url, params={"hook": "pl", "column": "X"}).status_code == 403
