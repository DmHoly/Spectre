"""Cahier de données (spectre.plugins.notebook): load a characterization data type
for an experience's plates, freeze it as a snapshot, and keep views on it (a visualization component
+ its settings) with notes - every change a new version, like the rest of the fiche. Uses the demo
data source (SPECTRE_DEMO_DATA=1) - PRISM itself needs real databases.
"""

from __future__ import annotations

import pytest

from spectre.plugins.attachments.store import attachments_dir
from spectre.plugins.characterization.source import DataSourceError
from spectre.plugins.notebook import snapshots

from support.accounts import login, signup
from support.experiments import get_experience, launch, timeline
from support.http import assert_handler_404
from support.microprojects import add_member, signup_with_microproject


@pytest.fixture()
def demo_data(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def _setup(client, email="notebook@example.com"):
    slug = signup_with_microproject(client, email, "Lots EQE", name="Chercheuse")
    launched = launch(
        client,
        slug,
        title="Pixélisation",
        intent="Même directivité",
        objectives=[{"name": "EQE identique", "metric": "max_EQE"}],
        entities=[{"sample_id": "W12-A3"}],
    )
    return slug, launched["id"]


def _snapshot(client, slug, hook="eqe", wafers=("W12-A3", "W12-A4")):
    return client.post(f"/api/microprojets/{slug}/donnees/instantanes", json={"hook": hook, "wafers": list(wafers)})


def test_compacting_drops_matrices_and_keeps_vectors_aligned():
    columns = ["wafer", "I", "EQE", "Spectra", "label"]
    rows = [["W1", list(range(300)), [v * 2 for v in range(300)], [[1, 2], [3, 4]], "a"]]
    out = snapshots.compact(columns, rows)
    assert out["columns"] == ["wafer", "I", "EQE", "label"] and out["dropped_columns"] == ["Spectra"]
    current, eqe = out["rows"][0][1], out["rows"][0][2]
    assert len(current) == snapshots.MAX_VECTOR_POINTS and current[0] == 0 and current[-1] == 299
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
    assert_handler_404(client.get(f"/api/microprojets/{slug}/donnees/instantanes/snap_{'0' * 20}"), "instantané introuvable")


def test_a_snapshot_id_cannot_reach_outside_the_attachments(client):
    slug, _ = _setup(client)
    # de vrais fichiers JSON qu'un id non vérifié atteindrait : sans eux, un 404 « instantané
    # introuvable » ne prouverait rien (il viendrait aussi d'un fichier simplement absent)
    attachments = attachments_dir(slug)
    (attachments / "secret.json").write_text('{"secret": true}', encoding="utf-8")
    (attachments.parent / "secret.json").write_text('{"secret": true}', encoding="utf-8")
    # an id still inside its own path segment reaches the handler, which refuses anything that isn't
    # a snapshot id (an encoded "../" never gets that far: the router has no route for it)
    assert_handler_404(client.get(f"/api/microprojets/{slug}/donnees/instantanes/secret"), "instantané introuvable")
    for snapshot_id in ("secret", "../secret", r"..\secret", "../attachments/secret"):
        with pytest.raises(DataSourceError) as exc_info:
            snapshots.load(slug, snapshot_id)
        assert exc_info.value.status_code == 404
        assert not snapshots.exists(slug, snapshot_id)


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
    entry = get_experience(client, slug, version)["data_notebook"][0]
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
    notebook = get_experience(client, slug, moved["id"])["data_notebook"]
    assert [e["title"] for e in notebook] == ["Carte EQE", "EQE vs J"]
    assert notebook[1]["note"] == "Conclusion : identique à 5 % près." and notebook[1]["in_report"] is False

    removed = client.delete(f"/api/microprojets/{slug}/experiences/{moved['id']}/cahier/{second['entry_id']}").json()
    notebook = get_experience(client, slug, removed["id"])["data_notebook"]
    assert [e["title"] for e in notebook] == ["EQE vs J"]
    # l'historique garde chaque étape (cahier de labo)
    assert len(timeline(client, slug, removed["id"])["items"]) == 5


def test_entries_are_validated(client, demo_data):
    slug, experience = _setup(client)
    snap = _snapshot(client, slug).json()
    url = f"/api/microprojets/{slug}/experiences/{experience}/cahier"
    base = {"title": "Vue", "snapshot_id": snap["snapshot_id"], "component": "table"}
    assert client.post(url, json={**base, "title": " "}).status_code == 422
    assert client.post(url, json={**base, "snapshot_id": "snap_" + "1" * 20}).status_code == 422
    assert client.post(url, json={**base, "component": "<script>"}).status_code == 422
    assert client.post(url, json={**base, "objective": "inexistant"}).status_code == 422
    assert_handler_404(client.put(f"{url}/nb_000000000000", json={"note": "x"}), "introuvable")
    assert_handler_404(client.delete(f"{url}/nb_000000000000"), "introuvable")


def test_viewers_read_the_notebook_but_do_not_change_it(client, demo_data):
    signup(client, "viewer-nb@example.com", name="V")
    slug, experience = _setup(client, "owner-nb@example.com")
    snap = _snapshot(client, slug).json()
    add_member(client, slug, "viewer-nb@example.com", "viewer")
    login(client, "viewer-nb@example.com")
    assert client.get(f"/api/microprojets/{slug}/donnees/instantanes/{snap['snapshot_id']}").status_code == 200
    assert _snapshot(client, slug).status_code == 403
    assert client.post(
        f"/api/microprojets/{slug}/experiences/{experience}/cahier",
        json={"title": "Vue", "snapshot_id": snap["snapshot_id"], "component": "table"},
    ).status_code == 403
