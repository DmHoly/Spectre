"""Le plugin wafer_data : les blocs de la fiche data d'un projet corporate, la fiche d'une plaque calculée sur la
démo (``SPECTRE_DEMO_DATA=1`` : aucun accès base) et gardée, résumée, dans le magasin à part du plugin."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import UpstreamError
from types import SimpleNamespace

from spectre.plugins.wafer_data import blocks, digest, store
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
    assert [k["key"] for k in catalog["kinds"]] == ["value", "histogram", "boxplot", "scatter", "wafermap", "curve", "images"]
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


def _columns(client, hook, slug=AREA):
    entry = next(h for h in client.get(f"{BASE.format(slug)}/catalog").json()["hooks"] if h["hook"] == hook)
    return {c["name"]: c for c in entry["columns"]}


def test_columns_are_typed_from_the_rows_actually_read(client):
    signup(client, "boss@example.com")
    before = _columns(client, "eqe")
    assert before["EQE"]["type"] == "vector" and not before["EQE"]["sure"]  # deviné sur la fiche PRISM
    assert before["pitch_nm"]["type"] == "number" and not before["pitch_nm"]["sure"]  # deviné sur « 800 », sa part de l'exemple « 800 / 400 / 1 »

    follow(client, "W1")
    probed = client.post(f"{BASE.format(AREA)}/catalog/eqe/probe", json={}).json()
    columns = {c["name"]: c for c in probed["columns"]}
    assert probed["observed_at"]
    assert {n: columns[n]["type"] for n in ("EQE", "V", "max_EQE", "is_lit", "Led_Name", "pitch_nm")} == {
        "EQE": "vector", "V": "vector", "max_EQE": "number", "is_lit": "flag", "Led_Name": "category", "pitch_nm": "number",
    }
    assert columns["EQE"]["sure"] and columns["EQE"]["observed"] and "valeurs" in columns["EQE"]["example"]
    assert "wafername" not in columns

    refused = add(client, "histogram", "eqe", column="EQE").json()
    assert refused["code"] == "wrong_column_type" and "vecteur" in refused["detail"]
    assert add(client, "curve", "eqe", x="Led_Name", y="max_EQE").json()["code"] == "wrong_column_type"
    assert add(client, "value", "eqe", column="is_lit", aggregate="median").json()["code"] == "invalid_aggregate"
    assert add(client, "value", "eqe", column="is_lit").json()["config"]["aggregate"] == "share"


def test_a_column_type_is_chosen_by_hand_for_every_project(client):
    signup(client, "boss@example.com")
    follow(client, "W1")
    client.post(f"{BASE.format(AREA)}/catalog/eqe/probe", json={})
    url = f"{BASE.format(AREA)}/catalog/eqe/columns"
    chosen = client.put(url, json={"column": "pitch_nm", "type": "category"}).json()
    pitch = next(c for c in chosen["columns"] if c["name"] == "pitch_nm")
    assert (pitch["type"], pitch["chosen"], pitch["observed_type"]) == ("category", "category", "number")
    other = client.post("/api/areas", json={"name": "Autre projet"}).json()["slug"]
    assert _columns(client, "eqe", slug=other)["pitch_nm"]["type"] == "category"  # une propriété de la donnée
    assert add(client, "histogram", "eqe", column="pitch_nm").json()["code"] == "wrong_column_type"
    assert client.put(url, json={"column": "pitch_nm", "type": "pixel"}).json()["code"] == "unknown_column_type"
    assert client.put(url, json={"column": "nope", "type": "number"}).json()["code"] == "unknown_column"
    reset = client.put(url, json={"column": "pitch_nm", "type": None}).json()
    assert next(c for c in reset["columns"] if c["name"] == "pitch_nm")["type"] == "number"

    signup(client, "user@example.com")
    login(client, "user@example.com")
    assert client.put(url, json={"column": "pitch_nm", "type": "category"}).status_code == 403


def test_probe_needs_a_wafer(client):
    signup(client, "boss@example.com")
    assert client.post(f"{BASE.format(AREA)}/catalog/eqe/probe", json={}).json()["code"] == "no_wafer_to_probe"
    assert client.post(f"{BASE.format(AREA)}/catalog/eqe/probe", json={"lasermark": "W9"}).json()["observed_at"]
    assert_handler_404(client.post(f"{BASE.format(AREA)}/catalog/inconnu/probe", json={"lasermark": "W9"}))


def test_curves_boxes_and_scatter_take_colours(client):
    signup(client, "boss@example.com")
    follow(client, "W1")
    client.post(f"{BASE.format(AREA)}/catalog/eqe/probe", json={})
    eqe_v = add(client, "curve", "eqe", x="V", y="EQE", color_by="pitch_nm", log_y=True).json()
    each = add(client, "curve", "eqe", x="V", y="EQE", mode="curves", color_by="Led_Name", label="Chaque courbe").json()
    box = add(client, "boxplot", "eqe", column="max_EQE", group_by="pitch_nm").json()
    cloud = add(client, "scatter", "eqe", x="J_at_MaxEQE", y="max_EQE", color_by="is_lit", color=3).json()
    hist = add(client, "histogram", "eqe", column="max_EQE", color_by="pitch_nm").json()
    assert eqe_v["title"] == "EQE en fonction de V" and box["title"] == "max_EQE par pitch_nm" and cloud["config"]["color"] == 3

    blocks = {b["id"]: b for b in client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"]}
    curve = blocks[eqe_v["id"]]
    assert curve["status"] == "ok" and curve["data"]["n"] > 50  # les NaN en tête des vecteurs ne font plus rejeter les courbes
    assert [s["label"] for s in curve["data"]["series"]] == ["600", "800", "1000"] and min(curve["data"]["low"]) > 0
    assert set(curve["units"]) == {"x", "y"}
    many = blocks[each["id"]]["data"]
    assert len(many["groups"]) == 8 and many["groups"][-1] == "Autres"  # plus de 8 devices : les autres regroupés
    assert 0 < len(many["curves"]) <= digest.MAX_CURVES and all(len(c["x"]) == len(c["y"]) for c in many["curves"])
    assert {c["g"] for c in many["curves"]} == set(range(8))  # chaque groupe a ses courbes
    boxes = blocks[box["id"]]["data"]["boxes"]
    assert [b["label"] for b in boxes] == ["600", "800", "1000"] and all(b["q1"] <= b["median"] <= b["q3"] for b in boxes)
    points = blocks[cloud["id"]]["data"]
    assert points["groups"] == ["faux", "vrai"] and len(points["points"]) == points["shown"] <= digest.MAX_POINTS
    histogram = blocks[hist["id"]]["data"]
    assert len(histogram["series"]) == 3 and sum(map(sum, histogram["series"])) == histogram["n"]


def test_images_from_a_column_of_links(client, monkeypatch, tmp_path):
    el_root = tmp_path / "el"
    monkeypatch.setenv("PRISM_EL_ROOT", str(el_root))
    signup(client, "boss@example.com")
    follow(client, "W1")
    probed = {c["name"]: c for c in client.post(f"{BASE.format(AREA)}/catalog/el_pattern/probe", json={}).json()["columns"]}
    assert probed["full_path"]["type"] == "image" and probed["name"]["type"] == "image" and probed["type"]["type"] == "category"
    assert add(client, "images", "el_pattern", column="led_name").json()["code"] == "wrong_column_type"
    block = add(client, "images", "el_pattern", column="full_path", group_by="type", caption=["led_name", "image_number"], max=3).json()
    assert block["title"] == "Images · full_path" and block["config"]["max"] == 3

    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(tmp_path / "ailleurs"))
    blocked = client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"][0]
    assert blocked["status"] == "error" and "hors des dossiers autorisés" in blocked["message"]

    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(tmp_path))
    data = client.get("/api/wafers/W1/data").json()["areas"][0]["blocks"][0]["data"]
    assert data["groups"] == ["LightImage", "LIVSweepImages"] and data["counts"] == [8, 12] and data["total"] == 20
    assert [i["g"] for i in data["images"]] == [0, 0, 1]  # tour à tour dans chaque groupe
    first = data["images"][0]
    assert set(first["meta"]) == {"led_name", "image_number"} and "path" not in first
    file = el_root / "W1" / "EL_Pattern" / first["name"]
    file.parent.mkdir(parents=True)
    file.write_bytes(b"\x89PNG el")
    assert client.get(first["url"]).content == b"\x89PNG el"


def test_columns_documented_together_each_get_their_own_example_and_type():
    """Une fiche PRISM documente parfois plusieurs colonnes d'un trait (« path / exists », exemple « …tif / true ») :
    chacune reçoit le sien - c'est ce qui fait du chemin des images MEB du G4 (meb_g4) un lien vers une image."""
    data_type = SimpleNamespace(
        key="meb_g4", title="Image MEB G4", category="Structure", representative_column="die",
        raw_columns=(
            {"name": "wafername", "example": "27CYH6E6MMC5"},
            {"name": "die / round", "example": "10 / 1"},
            {"name": "path / exists", "example": "N:\\ME-MEB101\\Datas\\Others\\w27CYH6E6MMC5\\d10r1_Class.tif / true"},
            {"name": "lot / fdl / process / step", "example": "2026-42070 / 2026-42070 / WLKGSM / ARC_POST_STRIP"},
            {"name": "modified / size", "example": "2026-10-17T01:40:24+00:00 / 2774495"},
            {"name": "x / y", "example": "pas découpable"},  # l'exemple ne se découpe pas : celui de la ligne d'exemple
        ),
        kpi_columns=(),
        example_rows=({"wafername": "27CYH6E6MMC5", "die": 10, "path": "N:\\d10r1_Class.tif", "x": 1.5, "y": -2.0},),
    )
    entry = blocks._entry(data_type, {}, [])
    types = {c["name"]: c["type"] for c in entry.columns}
    assert types["path"] == "image" and types["exists"] == "flag" and types["die"] == "number" and types["round"] == "number"
    assert types["fdl"] == "category" and types["modified"] == "date" and types["size"] == "number"
    assert types["x"] == "number" and types["y"] == "number" and (entry.x, entry.y) == ("x", "y")
    assert entry.column("path")["example"].endswith("d10r1_Class.tif") and entry.column("exists")["example"] == "true"
    assert entry.representative == "die"


def test_sem_images_of_a_block_are_served_by_the_sem_images_plugin(monkeypatch, tmp_path):
    """Les images du hook meb_g4 (des TIF du partage) ne passent pas par les images externes : la vignette et l'image
    entière viennent du plugin sem_images, par le chemin relatif à la racine du partage."""
    import spectre.plugins.sem_images  # noqa: F401 - déclare son serveur d'images à wafer_data
    from spectre.plugins.sem_images import service as sem_service
    from spectre.plugins.sem_images import source as sem_source
    from spectre.plugins.wafer_data import service

    root = tmp_path / "Datas"
    monkeypatch.setattr(sem_source, "root", lambda: root)
    block = blocks.Block(id=7, area_id=1, kind="images", hook="meb_g4", config={"column": "path", "caption": [], "max": 60}, label="", position=0, created_at="")
    found = {"status": "ok", "computed_at": "2026-10-19T10:00:00+00:00", "message": "", "payload": {"images": [
        {"path": str(root / "Others" / "l2026-42070_pWLKGSM_sARC" / "w27CYH6E6MMC5" / "d10r1_Class.tif"), "name": "d10r1_Class.tif", "meta": {}, "g": 0},
        {"path": "D:/ailleurs/autre.tif", "name": "autre.tif", "meta": {}, "g": 0},
    ], "total": 2}}
    shown = service.block_payload(block, found, wafer="27CYH6E6MMC5", entries={})
    first, second = shown["data"]["images"]
    assert first["url"] == "/api/wafers/27CYH6E6MMC5/sem-images/file?path=Others/l2026-42070_pWLKGSM_sARC/w27CYH6E6MMC5/d10r1_Class.tif&variant=thumb"
    assert first["full"].endswith("d10r1_Class.tif&variant=view")
    assert second["url"] == "/api/wafers/27CYH6E6MMC5/data/images/7/1" and "full" not in second  # hors de la racine : l'adresse ordinaire

    status, message = service._served("ok", {"images": found["payload"]["images"]}, "meb_g4")
    assert status == "ok" and message == ""  # pas de contrôle des dossiers autorisés pour le partage MEB
    monkeypatch.setattr(sem_service.plugin_states, "is_enabled", lambda name: name != "sem_images")
    shown = service.block_payload(block, found, wafer="27CYH6E6MMC5", entries={})
    assert shown["data"]["images"][0]["url"] == "/api/wafers/27CYH6E6MMC5/data/images/7/0"  # plugin éteint : l'adresse ordinaire


def test_curve_digest_skips_missing_points():
    columns = ["wafername", "V", "EQE", "kind"]
    rows = [["W", [0.0, 1.0, 2.0, 3.0], [None, None, 0.1 * k, 0.2 * k], "a" if k < 3 else "b"] for k in range(1, 6)]
    status, payload, _ = digest.curve(columns, rows, {"x": "V", "y": "EQE", "color_by": "kind", "filters": [], "date": "all"})
    assert status == "ok" and payload["n"] == 5 and payload["x"][0] == 2.0
    assert [(s["label"], s["n"]) for s in payload["series"]] == [("a", 2), ("b", 3)]
    status, _, _ = digest.curve(columns, [["W", [0.0, 1.0], [None, None], "a"]], {"x": "V", "y": "EQE", "filters": [], "date": "all"})
    assert status == "empty"


def test_spread_shares_the_rows_between_groups():
    alternating = [0, 1, 2] * 30  # un pas fixe de 3 ne verrait que le groupe 0
    chosen = digest.spread(alternating, 12)
    assert len(chosen) == 12 and [alternating[i] for i in chosen].count(0) == 4
    assert digest.spread([0, 0, 1], 5) == [0, 1, 2]
    lopsided = digest.spread([0] * 100 + [1] * 2, 10)
    assert len(lopsided) == 10 and {100, 101} <= set(lopsided)
