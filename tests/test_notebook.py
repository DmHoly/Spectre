"""Cahier de données (spectre.api.notebook / spectre.core.datasets): load a characterization data type
for an experience's plates, freeze it as a snapshot, and keep views on it (a visualization component
+ its settings) with notes - every change a new version, like the rest of the fiche. Uses the demo
data source (SPECTRE_DEMO_DATA=1) - PRISM itself needs real databases.
"""

from __future__ import annotations

import pytest

from spectre.core import datasets


@pytest.fixture()
def demo_data(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": 20, "unit": "nm"}}]


def _setup(client, email="notebook@example.com"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "Chercheuse"})
    slug = client.post("/api/microprojets", json={"name": "Lots EQE"}).json()["slug"]
    launched = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Pixélisation",
            "intent": "Même directivité",
            "objectives": [{"name": "EQE identique", "metric": "max_EQE"}],
            "entities": [{"sample_id": "W12-A3"}],
        },
    ).json()
    return slug, launched["id"]


def _snapshot(client, slug, hook="eqe", wafers=("W12-A3", "W12-A4")):
    return client.post(f"/api/microprojets/{slug}/donnees/instantanes", json={"hook": hook, "wafers": list(wafers)})


def test_compacting_drops_matrices_and_keeps_vectors_aligned():
    columns = ["wafer", "I", "EQE", "Spectra", "label"]
    rows = [["W1", list(range(300)), [v * 2 for v in range(300)], [[1, 2], [3, 4]], "a"]]
    out = datasets.compact(columns, rows)
    assert out["columns"] == ["wafer", "I", "EQE", "label"] and out["dropped_columns"] == ["Spectra"]
    current, eqe = out["rows"][0][1], out["rows"][0][2]
    assert len(current) == datasets.MAX_VECTOR_POINTS and current[0] == 0 and current[-1] == 299
    assert eqe == [v * 2 for v in current]  # mêmes indices pour I et EQE


def test_sources_list_the_implemented_prism_types(client, demo_data):
    slug, _ = _setup(client)
    body = client.get(f"/api/microprojets/{slug}/donnees/sources").json()
    keys = {s["key"] for s in body["sources"]}
    assert {"eqe", "pl", "ncel"} <= keys and "tem" not in keys  # pas les fiches « à venir »
    assert body["demo"] is True


def test_a_snapshot_freezes_the_data_of_the_plates(client, demo_data):
    slug, _ = _setup(client)
    response = _snapshot(client, slug)
    assert response.status_code == 201
    snap = response.json()
    assert snap["source"] == "demo" and snap["hook"] == "eqe" and snap["wafers"] == ["W12-A3", "W12-A4"]
    assert {"wafername", "X", "Y", "max_EQE", "I", "EQE"} <= set(snap["columns"])
    wafer_col = snap["columns"].index("wafername")
    assert {row[wafer_col] for row in snap["rows"]} == {"W12-A3", "W12-A4"}
    again = client.get(f"/api/microprojets/{slug}/donnees/instantanes/{snap['snapshot_id']}").json()
    assert again["rows"] == snap["rows"]
    # même plaque, mêmes données de démo
    assert _snapshot(client, slug).json()["rows"] == snap["rows"]
    assert client.get(f"/api/microprojets/{slug}/donnees/instantanes/snap_{'0' * 20}").status_code == 404
    assert client.get(f"/api/microprojets/{slug}/donnees/instantanes/..%2Fspectre").status_code == 404


def test_a_snapshot_needs_plates_and_a_known_type(client, demo_data):
    slug, _ = _setup(client)
    assert _snapshot(client, slug, wafers=()).status_code == 422
    assert _snapshot(client, slug, hook="inconnu").status_code == 422


def test_without_demo_data_prism_errors_are_readable(client, monkeypatch):
    monkeypatch.delenv("SPECTRE_DEMO_DATA", raising=False)
    slug, _ = _setup(client)

    def broken(*args, **kwargs):
        import prism

        raise prism.ConfigError("identifiants introuvables")

    import prism

    monkeypatch.setattr(prism, "run_hook_cached", broken)
    response = _snapshot(client, slug)
    assert response.status_code == 400 and "PRISM" in response.json()["detail"]


def test_notebook_entries_are_versioned_with_their_notes(client, demo_data):
    slug, experience = _setup(client)
    snap = _snapshot(client, slug).json()
    added = client.post(
        f"/api/microprojets/{slug}/experiences/{experience}/cahier",
        json={
            "title": "EQE vs J",
            "snapshot_id": snap["snapshot_id"],
            "component": "eqe-curves",
            "options": {"maxCurves": 30},
            "note": "  Pas d'écart pixel / non pixel.  ",
            "objective": "EQE identique",
        },
    )
    assert added.status_code == 201
    version = added.json()["id"]
    entry = client.get(f"/api/microprojets/{slug}/experiences/{version}").json()["data_notebook"][0]
    assert entry["title"] == "EQE vs J" and entry["note"] == "Pas d'écart pixel / non pixel."
    assert entry["hook"] == "eqe" and entry["source"] == "demo" and entry["wafers"] == ["W12-A3", "W12-A4"]
    assert entry["created_by"] == "Chercheuse" and entry["in_report"] is True and entry["objective"] == "EQE identique"

    second = client.post(
        f"/api/microprojets/{slug}/experiences/{version}/cahier",
        json={"title": "Carte EQE", "snapshot_id": snap["snapshot_id"], "component": "wafer-map", "options": {"value": "max_EQE"}},
    ).json()
    entry_id = entry["id"]
    moved = client.put(
        f"/api/microprojets/{slug}/experiences/{second['id']}/cahier/{entry_id}",
        json={"note": "Conclusion : identique à 5 % près.", "move": 1, "in_report": False},
    ).json()
    notebook = client.get(f"/api/microprojets/{slug}/experiences/{moved['id']}").json()["data_notebook"]
    assert [e["title"] for e in notebook] == ["Carte EQE", "EQE vs J"]
    assert notebook[1]["note"] == "Conclusion : identique à 5 % près." and notebook[1]["in_report"] is False

    removed = client.delete(f"/api/microprojets/{slug}/experiences/{moved['id']}/cahier/{second['entry_id']}").json()
    notebook = client.get(f"/api/microprojets/{slug}/experiences/{removed['id']}").json()["data_notebook"]
    assert [e["title"] for e in notebook] == ["EQE vs J"]
    # l'historique garde chaque étape (cahier de labo)
    items = client.get(f"/api/microprojets/{slug}/experiences/{removed['id']}/timeline").json()["items"]
    assert len(items) == 5


def test_entries_are_validated(client, demo_data):
    slug, experience = _setup(client)
    snap = _snapshot(client, slug).json()
    url = f"/api/microprojets/{slug}/experiences/{experience}/cahier"
    base = {"title": "Vue", "snapshot_id": snap["snapshot_id"], "component": "table"}
    assert client.post(url, json={**base, "title": " "}).status_code == 422
    assert client.post(url, json={**base, "snapshot_id": "snap_" + "1" * 20}).status_code == 422
    assert client.post(url, json={**base, "component": "<script>"}).status_code == 422
    assert client.post(url, json={**base, "objective": "inexistant"}).status_code == 422
    assert client.put(f"{url}/nb_000000000000", json={"note": "x"}).status_code == 404


def test_viewers_read_the_notebook_but_do_not_change_it(client, demo_data):
    client.post("/api/auth/register", json={"email": "viewer-nb@example.com", "password": "supersecret", "name": "V"})
    slug, experience = _setup(client, "owner-nb@example.com")
    snap = _snapshot(client, slug).json()
    assert client.post(f"/api/microprojets/{slug}/members", json={"email": "viewer-nb@example.com", "role": "viewer"}).status_code == 201
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "viewer-nb@example.com", "password": "supersecret"})
    assert client.get(f"/api/microprojets/{slug}/donnees/instantanes/{snap['snapshot_id']}").status_code == 200
    assert _snapshot(client, slug).status_code == 403
    assert client.post(
        f"/api/microprojets/{slug}/experiences/{experience}/cahier",
        json={"title": "Vue", "snapshot_id": snap["snapshot_id"], "component": "table"},
    ).status_code == 403
