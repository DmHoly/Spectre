"""Le plugin wafer_data : les blocs de la fiche data d'un projet corporate, la fiche d'une plaque calculée sur la
démo (``SPECTRE_DEMO_DATA=1`` : aucun accès base) et gardée, résumée, dans le magasin à part du plugin."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import UpstreamError
from spectre.plugins.wafer_data import digest, store
from support.accounts import login, signup
from support.experiments import launch
from support.http import assert_handler_404
from support.microprojects import create_microproject

AREA = "native-pt2"
BASE = "/api/areas/{}/wafer-data"


@pytest.fixture(autouse=True)
def demo_source(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def add(client, kind, hook="", slug=AREA, label=None, **config):
    return client.post(f"{BASE.format(slug)}/blocks", json={"kind": kind, "hook": hook, "config": config, "label": label})


def follow(client, *wafers, area=AREA, name="Suivi data"):
    slug = create_microproject(client, name, area=area)["slug"]
    launch(client, slug, title="Essai", intent="x", entities=[{"sample_id": w} for w in wafers])
    return slug


def test_the_catalog_lists_per_wafer_types_with_their_columns(client):
    signup(client, "boss@example.com")
    catalog = client.get(f"{BASE.format(AREA)}/catalog").json()
    hooks = {h["hook"]: h for h in catalog["hooks"]}
    assert {"eqe", "pl"} <= set(hooks)
    pl = hooks["pl"]
    assert (pl["x"], pl["y"], pl["dated"]) == ("X", "Y", True)
    names = [c["name"] for c in pl["columns"]]
    assert "Dominant WL(nm)" in names and not [n for n in names if n.lower() in ("wafername", "wafer name")]
    assert [k["key"] for k in catalog["kinds"]] == ["value", "histogram", "wafermap", "curve", "images"]
    assert_handler_404(client.get(f"{BASE.format('inconnu')}/catalog"))


def test_configure_blocks(client):
    signup(client, "boss@example.com")
    value = add(client, "value", "eqe", column="max_EQE", aggregate="median", better="high")
    assert value.status_code == 201 and value.headers["Location"].endswith(f"/blocks/{value.json()['id']}")
    assert value.json()["title"] == "max_EQE (médiane)"
    wafermap = add(client, "wafermap", "pl", column="Dominant WL(nm)", label="  Carte   PL ").json()
    assert wafermap["config"]["x"] == "X" and wafermap["config"]["y"] == "Y" and wafermap["title"] == "Carte PL"
    assert wafermap["config"]["date"] == "latest" and wafermap["config"]["filters"] == []

    assert add(client, "value", "eqe", column="n_existe_pas").json()["code"] == "unknown_column"
    assert add(client, "value", "inconnu", column="x").json()["code"] == "unknown_hook"
    assert add(client, "value", "eqe", column="max_EQE", aggregate="mode").json()["code"] == "unknown_aggregate"
    assert add(client, "histogram", "pl", column="FWHM (nm)", filters=[{"column": "Nope", "op": "eq", "value": "x"}]).json()["code"] == "unknown_filter_column"
    assert add(client, "images", pattern="D:/mesures/*.png").json()["code"] == "pattern_without_wafer"
    assert add(client, "images", pattern="D:/mesures/{wafer}/*.png").json()["code"] == "unknown_placeholder"
    assert add(client, "images", pattern="D:/*/{lasermark}.png").json()["code"] == "invalid_pattern"
    images = add(client, "images", pattern="D:/mesures/{lot}/{lasermark}_*.png", max=99).json()
    assert images["hook"] == "" and images["config"]["max"] == 24

    blocks = client.get(f"{BASE.format(AREA)}/blocks").json()
    assert [b["kind"] for b in blocks] == ["value", "wafermap", "images"]
    moved = client.patch(f"{BASE.format(AREA)}/blocks/{images['id']}", json={"move": "up"})
    assert moved.status_code == 200
    assert [b["kind"] for b in client.get(f"{BASE.format(AREA)}/blocks").json()] == ["value", "images", "wafermap"]
    renamed = client.patch(f"{BASE.format(AREA)}/blocks/{wafermap['id']}", json={"label": ""}).json()
    assert renamed["title"] == "Dominant WL(nm)"
    assert client.delete(f"{BASE.format(AREA)}/blocks/{images['id']}").status_code == 204
    assert_handler_404(client.delete(f"{BASE.format(AREA)}/blocks/{images['id']}"))
    other = client.post("/api/areas", json={"name": "Autre projet"}).json()["slug"]
    assert client.get(f"{BASE.format(other)}/blocks").json() == []
    assert_handler_404(client.patch(f"{BASE.format(other)}/blocks/{value.json()['id']}", json={"label": "x"}))


def test_only_a_project_manager_changes_blocks(client):
    signup(client, "boss@example.com")  # le premier compte est administrateur
    signup(client, "user@example.com")
    login(client, "user@example.com")
    assert client.get(f"{BASE.format(AREA)}/blocks").status_code == 200
    assert add(client, "value", "eqe", column="max_EQE").status_code == 403


def test_a_wafer_without_microproject_has_no_data_sheet(client):
    signup(client, "boss@example.com")
    add(client, "value", "eqe", column="max_EQE")
    sheet = client.get("/api/wafers/W1/data").json()
    assert sheet["areas"] == [] and sheet["wafer"]["key"] == "W1"


def test_the_sheet_of_a_wafer_computes_then_reads_back_its_digests(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization

    signup(client, "boss@example.com")
    slug = follow(client, "W1", "W2", "W3")
    value = add(client, "value", "eqe", column="max_EQE", better="high").json()
    share = add(client, "value", "eqe", column="is_lit", aggregate="share").json()
    add(client, "histogram", "pl", column="Integrated PL (a.u.)")
    add(client, "wafermap", "pl", column="Dominant WL(nm)")
    add(client, "curve", "eqe", x="I", y="EQE", log_x=True)
    add(client, "curve", "eqe", x="Led_Name", y="max_EQE", label="Pas une courbe")

    calls = []
    real = characterization.query

    def counting(key, parameters, *, refresh=False):
        calls.append((key, tuple(parameters["wafer_names"]), refresh))
        return real(key, parameters, refresh=refresh)

    monkeypatch.setattr(characterization, "query", counting)
    sheet = client.get("/api/wafers/w1/data").json()
    assert sheet["source"] == "demo" and sheet["wafer"]["lasermark"] == "W1"
    (area,) = sheet["areas"]
    assert area["area"]["slug"] == AREA and area["can_manage"] and [m["slug"] for m in area["microprojects"]] == [slug]
    assert sorted(calls) == [("eqe", ("W1",), False), ("pl", ("W1",), False)]  # un type de données, une requête
    by_title = {b["title"]: b for b in area["blocks"]}

    median = by_title["max_EQE (médiane)"]
    assert median["status"] == "ok" and median["data"]["value"] > 0 and median["data"]["n"] > 50 and median["computed_at"]
    assert median["population"] is None  # seule plaque calculée du projet : rien à quoi la comparer
    assert 0 <= by_title["is_lit (part vraie)"]["data"]["value"] <= 100 and by_title["is_lit (part vraie)"]["unit"] == "%"

    histogram = by_title["Integrated PL (a.u.)"]["data"]
    assert sum(histogram["counts"]) == histogram["n"] and len(histogram["counts"]) == digest.HISTOGRAM_BINS
    assert histogram["date"] == histogram["dates"][-1]  # la mesure la plus récente seulement

    wafermap = by_title["Dominant WL(nm)"]["data"]
    assert len(wafermap["values"]) == len(wafermap["ys"]) and all(len(r) == len(wafermap["xs"]) for r in wafermap["values"])
    assert wafermap["minimum"] <= wafermap["median"] <= wafermap["maximum"]

    curve = by_title["EQE en fonction de I"]["data"]
    assert curve["n"] > 50 and len(curve["x"]) == len(curve["median"]) == len(curve["low"]) == len(curve["high"])
    assert all(lo <= m <= hi for lo, m, hi in zip(curve["low"], curve["median"], curve["high"]))
    assert by_title["Pas une courbe"]["status"] == "empty" and by_title["Pas une courbe"]["data"]["reason"] == "not_vectors"

    calls.clear()
    again = client.get("/api/wafers/W1/data").json()
    assert calls == []  # tout est relu du magasin
    assert {b["id"]: b["data"] for b in again["areas"][0]["blocks"]} == {b["id"]: b["data"] for b in area["blocks"]}

    client.get("/api/wafers/W2/data")
    client.get("/api/wafers/W3/data")
    ranked = next(b for b in client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"] if b["id"] == value["id"])
    population = ranked["population"]
    assert population["count"] == 3 and population["below"] + population["equal"] <= 3 and sum(population["bins"]) == 3

    calls.clear()
    client.get("/api/wafers/W1/data?refresh=true")
    assert sorted(calls) == [("eqe", ("W1",), True), ("pl", ("W1",), True)]
    assert share["id"]


def test_a_failing_type_leaves_the_others_and_is_not_kept(client, monkeypatch):
    from spectre.plugins.characterization import service as characterization

    signup(client, "boss@example.com")
    follow(client, "W1")
    add(client, "value", "eqe", column="max_EQE")
    add(client, "value", "pl", column="FWHM (nm)")
    real = characterization.query

    def flaky(key, parameters, *, refresh=False):
        if key == "eqe":
            raise UpstreamError("la requête PRISM a échoué : base injoignable")
        return real(key, parameters, refresh=refresh)

    monkeypatch.setattr(characterization, "query", flaky)
    blocks = {b["hook"]: b for b in client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"]}
    assert blocks["eqe"]["status"] == "error" and "injoignable" in blocks["eqe"]["message"]
    assert blocks["pl"]["status"] == "ok"
    monkeypatch.setattr(characterization, "query", real)
    blocks = {b["hook"]: b for b in client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"]}
    assert blocks["eqe"]["status"] == "ok"  # l'erreur n'avait rien gardé


def test_changing_a_block_forgets_what_it_computed(client):
    signup(client, "boss@example.com")
    follow(client, "W1")
    block = add(client, "value", "eqe", column="max_EQE").json()
    client.get("/api/wafers/W1/data")
    assert store.stats()["digests"] == 1
    changed = client.patch(f"{BASE.format(AREA)}/blocks/{block['id']}", json={"config": {"column": "max_EQE", "aggregate": "max"}}).json()
    assert changed["title"] == "max_EQE (max)" and store.stats()["digests"] == 0
    client.get("/api/wafers/W1/data")
    client.delete(f"{BASE.format(AREA)}/blocks/{block['id']}")
    assert store.stats()["digests"] == 0 and store.stats()["scalars"] == 0


def test_compute_a_whole_project_by_batches(client, monkeypatch):
    from spectre.plugins.wafer_data import service

    monkeypatch.setattr(service, "BATCH", 2)
    signup(client, "boss@example.com")
    follow(client, "W1", "W2", "W3")
    add(client, "value", "eqe", column="max_EQE")
    first = client.post(f"{BASE.format(AREA)}/compute").json()
    assert (first["total"], first["done"], first["next_offset"], first["computed"]) == (3, 2, 2, 2)
    second = client.post(f"{BASE.format(AREA)}/compute?offset=2").json()
    assert (second["done"], second["next_offset"], second["computed"]) == (3, None, 1)
    assert client.post(f"{BASE.format(AREA)}/compute").json()["computed"] == 0  # rien ne manque
    assert store.stats()["scalars"] == 3


def test_images_are_found_from_the_pattern_under_the_allowed_roots(client, monkeypatch, tmp_path):
    root = tmp_path / "mesures"
    (root / "W1").mkdir(parents=True)
    for name in ("W1_pl.png", "W1_sem.jpg", "notes.txt", "W1_raw.tif"):
        (root / "W1" / name).write_bytes(b"\x89PNG fake")
    signup(client, "boss@example.com")
    follow(client, "W1", "W2")
    block = add(client, "images", pattern=str(root) + "/{lasermark}/{lasermark}_*").json()

    disabled = client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"][0]
    assert disabled["status"] == "error" and "pas activées" in disabled["message"]

    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(tmp_path))
    found = client.get("/api/wafers/W1/data?refresh=true").json()["areas"][0]["blocks"][0]
    assert found["status"] == "ok" and [i["name"] for i in found["data"]["images"]] == ["W1_pl.png", "W1_sem.jpg"]
    assert "path" not in found["data"]["images"][0]  # le chemin reste sur le serveur
    image = client.get(found["data"]["images"][0]["url"])
    assert image.status_code == 200 and image.content == b"\x89PNG fake"
    assert_handler_404(client.get(f"/api/wafers/W1/data/images/{block['id']}/9"))

    missing = client.get("/api/wafers/W2/data").json()["areas"][0]["blocks"][0]
    assert missing["status"] == "empty"


def test_the_budget_forgets_the_least_recently_read_digests_but_keeps_values(client, monkeypatch):
    signup(client, "boss@example.com")
    follow(client, "W1", "W2")
    add(client, "value", "eqe", column="max_EQE")
    add(client, "wafermap", "pl", column="Dominant WL(nm)")
    client.get("/api/wafers/W1/data")
    client.get("/api/wafers/W2/data")
    before = store.stats()
    assert before["digests"] == 4 and before["scalars"] == 2
    monkeypatch.setattr(store, "budget_bytes", lambda: before["payload_bytes"] // 2)
    assert store.enforce_budget() >= 1
    after = store.stats()
    assert after["digests"] < 4 and after["scalars"] == 2
    assert client.get("/api/wafer-data/storage").json()["digests"] == after["digests"]


def test_digest_helpers():
    columns = ["wafername", "X", "Y", "v", "date"]
    rows = [["W", x, y, float(x + y), "2026-01-01" if x < 2 else "2026-02-01"] for x in range(4) for y in range(3)]
    status, payload, scalar = digest.value(columns, rows, {"column": "v", "aggregate": "max", "filters": [], "date": "all"})
    assert (status, payload["value"], scalar) == ("ok", 5.0, 5.0)
    status, latest, _ = digest.wafermap(columns, rows, {"column": "v", "x": "X", "y": "Y", "filters": [], "date": "latest"})
    assert latest["date"] == "2026-02-01" and latest["xs"] == [2.0, 3.0] and latest["values"][0] == [2.0, 3.0]
    many = [["W", float(i), 0.0, 1.0, None] for i in range(500)]
    _, big, _ = digest.wafermap(columns, many, {"column": "v", "x": "X", "y": "Y", "filters": [], "date": "all"})
    assert len(big["xs"]) == digest.MAX_GRID  # une cartographie fine est ramenée à la grille
    assert digest.round4(123456.789) == 123500.0
