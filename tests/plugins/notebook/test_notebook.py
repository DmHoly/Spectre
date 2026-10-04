"""Cahier de données (plugin notebook) : charger un type de données de caractérisation pour les
plaques d'une étude, le figer en instantané, et garder des vues dessus (un composant de
visualisation + ses réglages) avec des notes - chaque changement une écriture sur la piste, comme le
reste de la fiche. Utilise la source de démonstration (SPECTRE_DEMO_DATA=1) : PRISM lui-même demande
de vraies bases.
"""

from __future__ import annotations

import json

import pytest

from spectre.kernel.errors import NotFound
from spectre.plugins.attachments.store import attachments_dir
from spectre.plugins.notebook import snapshots

from support.accounts import login, signup
from support.characterization import list_data_types
from support.experiments import get_experiment, launch, tag, versions
from support.http import assert_handler_404
from support.microprojects import add_member, signup_with_microproject
from support.notebook import (
    add_entry,
    delete_entry,
    entries,
    get_snapshot,
    patch_entry,
    post_entry,
    post_snapshot,
    take_snapshot,
    update_entry,
)


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
        hypothesis="La pixélisation ne change rien",
        objectives=[{"name": "EQE identique", "metric": "max_EQE"}],
        entities=[{"sample_id": "W12-A3"}],
    )
    return slug, launched["id"]


def test_compacting_drops_matrices_and_keeps_vectors_aligned():
    columns = ["wafer", "I", "EQE", "Spectra", "label"]
    rows = [["W1", list(range(300)), [v * 2 for v in range(300)], [[1, 2], [3, 4]], "a"]]
    out = snapshots.compact(columns, rows)
    assert out["columns"] == ["wafer", "I", "EQE", "label"] and out["dropped_columns"] == ["Spectra"]
    current, eqe = out["rows"][0][1], out["rows"][0][2]
    assert len(current) == snapshots.MAX_VECTOR_POINTS and current[0] == 0 and current[-1] == 299
    assert eqe == [v * 2 for v in current]  # mêmes indices pour I et EQE


def test_the_loadable_types_come_from_the_characterization_catalogue(client, demo_data):
    # la liste du cahier (l'ancienne route /donnees/sources) : les types implémentés, par plaque
    signup(client, "catalogue@example.com")
    keys = {t["key"] for t in list_data_types(client, by_wafer="true", status="implemented")}
    assert {"eqe", "pl", "ncel"} <= keys and "tem" not in keys  # pas les fiches « à venir »


def test_a_snapshot_freezes_the_data_of_the_plates(client, demo_data):
    slug, _ = _setup(client)
    response = post_snapshot(client, slug)
    assert response.status_code == 201
    snap = response.json()
    assert response.headers["Location"] == f"/api/microprojects/{slug}/snapshots/{snap['snapshot_id']}"
    assert snap["source"] == "demo" and snap["hook"] == "eqe" and snap["wafers"] == ["W12-A3", "W12-A4"]
    assert {"wafername", "X", "Y", "max_EQE", "I", "EQE"} <= set(snap["columns"])
    wafer_col = snap["columns"].index("wafername")
    assert {row[wafer_col] for row in snap["rows"]} == {"W12-A3", "W12-A4"}

    again = get_snapshot(client, slug, snap["snapshot_id"])
    assert again.json()["rows"] == snap["rows"]
    assert "immutable" in again.headers["Cache-Control"]  # un instantané ne change jamais
    # même plaque, mêmes données de démo
    assert take_snapshot(client, slug)["rows"] == snap["rows"]
    assert_handler_404(get_snapshot(client, slug, f"snap_{'0' * 20}"), "instantané introuvable")


def test_new_snapshots_have_their_own_folder_and_old_ones_stay_readable(client, demo_data):
    slug, _ = _setup(client)
    snap = take_snapshot(client, slug)
    assert (snapshots.snapshots_dir(slug) / f"{snap['snapshot_id']}.json").is_file()
    assert not (attachments_dir(slug) / f"{snap['snapshot_id']}.json").exists()

    # un instantané d'avant ce dossier, rangé avec les pièces jointes
    old_id = f"snap_{'a' * 20}"
    (attachments_dir(slug) / f"{old_id}.json").write_text(json.dumps({"hook": "eqe", "rows": [[1]], "columns": ["x"]}), encoding="utf-8")
    assert get_snapshot(client, slug, old_id).json()["rows"] == [[1]]


def test_a_snapshot_id_cannot_reach_outside_its_folders(client):
    slug, _ = _setup(client)
    # de vrais fichiers JSON qu'un id non vérifié atteindrait : sans eux, un 404 « instantané
    # introuvable » ne prouverait rien (il viendrait aussi d'un fichier simplement absent)
    for directory in (attachments_dir(slug), snapshots.snapshots_dir(slug)):
        (directory / "secret.json").write_text('{"secret": true}', encoding="utf-8")
        (directory.parent / "secret.json").write_text('{"secret": true}', encoding="utf-8")
    # un id resté dans son segment atteint la route, qui refuse tout ce qui n'est pas un id
    # d'instantané (un « ../ » encodé n'arrive pas jusque-là : le routeur n'a pas de route pour lui)
    assert_handler_404(get_snapshot(client, slug, "secret"), "instantané introuvable")
    for snapshot_id in ("secret", "../secret", r"..\secret", "../attachments/secret", "../snapshots/secret"):
        with pytest.raises(NotFound):
            snapshots.load(slug, snapshot_id)
        assert not snapshots.exists(slug, snapshot_id)


def test_a_snapshot_needs_plates_and_a_known_type(client, demo_data):
    slug, _ = _setup(client)
    assert post_snapshot(client, slug, wafers=()).status_code == 422
    assert_handler_404(post_snapshot(client, slug, hook="inconnu"), "type de données inconnu")


def test_without_demo_data_prism_errors_are_readable(client, monkeypatch):
    monkeypatch.delenv("SPECTRE_DEMO_DATA", raising=False)
    slug, _ = _setup(client)

    def broken(*args, **kwargs):
        import prism

        raise prism.ConfigError("identifiants introuvables")

    import prism

    monkeypatch.setattr(prism, "run_hook_cached", broken)
    response = post_snapshot(client, slug)
    assert response.status_code == 503 and "PRISM" in response.json()["detail"]


def test_notebook_entries_are_versioned_with_their_notes(client, demo_data):
    slug, line = _setup(client)
    snap = take_snapshot(client, slug)
    first_version = get_experiment(client, slug, line)["version_id"]
    response = post_entry(
        client,
        slug,
        line,
        title="EQE vs J",
        snapshot_id=snap["snapshot_id"],
        component="eqe-curves",
        options={"maxCurves": 30},
        note="  Pas d'écart pixel / non pixel.  ",
        objective="EQE identique",
    )
    assert response.status_code == 201
    entry = response.json()
    assert response.headers["ETag"] == f'"{get_experiment(client, slug, line)["version_id"]}"'
    assert entry["title"] == "EQE vs J" and entry["note"] == "Pas d'écart pixel / non pixel."
    assert entry["hook"] == "eqe" and entry["source"] == "demo" and entry["wafers"] == ["W12-A3", "W12-A4"]
    assert entry["created_by"] == "Chercheuse" and entry["in_report"] is True and entry["objective"] == "EQE identique"
    assert entries(client, slug, line) == [entry]
    # le détail de l'étude ne porte plus le cahier : le panneau lit sa propre ressource
    assert "data_notebook" not in get_experiment(client, slug, line)

    second = add_entry(client, slug, line, snap["snapshot_id"], title="Carte EQE", component="wafer-map", options={"value": "max_EQE"})
    moved = update_entry(client, slug, line, entry["id"], note="Conclusion : identique à 5 % près.", position=1, in_report=False)
    assert moved["note"] == "Conclusion : identique à 5 % près." and moved["in_report"] is False
    notebook = entries(client, slug, line)
    assert [e["title"] for e in notebook] == ["Carte EQE", "EQE vs J"]
    assert notebook[1] == moved
    # une place hors des bornes est ramenée dans le cahier
    update_entry(client, slug, line, entry["id"], position=-5)
    assert [e["title"] for e in entries(client, slug, line)] == ["EQE vs J", "Carte EQE"]

    removed = delete_entry(client, slug, line, second["id"])
    assert removed.status_code == 204 and removed.content == b""
    assert [e["title"] for e in entries(client, slug, line)] == ["EQE vs J"]
    # l'historique garde chaque étape (cahier de labo), et une version passée se relit
    assert len(versions(client, slug, line)) == 6
    assert entries(client, slug, line, version=first_version) == []
    # aucune écriture du cahier ne perd l'hypothèse
    assert get_experiment(client, slug, line)["hypothesis"] == "La pixélisation ne change rien"


def test_a_change_without_effect_creates_no_version(client, demo_data):
    slug, line = _setup(client)
    entry = add_entry(client, slug, line, take_snapshot(client, slug)["snapshot_id"], note="Vu")
    count = len(versions(client, slug, line))
    again = update_entry(client, slug, line, entry["id"], note="Vu", title="Vue", position=0)
    assert again == entry
    assert len(versions(client, slug, line)) == count


def test_an_objective_can_be_cleared(client, demo_data):
    slug, line = _setup(client)
    entry = add_entry(client, slug, line, take_snapshot(client, slug)["snapshot_id"], objective="EQE identique")
    assert update_entry(client, slug, line, entry["id"], objective="")["objective"] is None


def test_entries_are_validated(client, demo_data):
    slug, line = _setup(client)
    snap = take_snapshot(client, slug)
    base = {"title": "Vue", "snapshot_id": snap["snapshot_id"], "component": "table"}
    assert post_entry(client, slug, line, **{**base, "title": " "}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "snapshot_id": "snap_" + "1" * 20}).json()["code"] == "snapshot_not_found"
    assert post_entry(client, slug, line, **{**base, "component": "<script>"}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "objective": "inexistant"}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "options": {"x": "a" * 20001}}).status_code == 422
    entry = add_entry(client, slug, line, snap["snapshot_id"])
    assert patch_entry(client, slug, line, entry["id"], title="").status_code == 422
    assert_handler_404(patch_entry(client, slug, line, "nb_000000000000", note="x"), "introuvable")
    assert_handler_404(delete_entry(client, slug, line, "nb_000000000000"), "introuvable")
    assert_handler_404(post_entry(client, slug, "piste-inconnue", **base), "introuvable")


def test_a_stale_if_match_is_refused_on_every_write(client, demo_data):
    slug, line = _setup(client)
    snap = take_snapshot(client, slug)
    entry = add_entry(client, slug, line, snap["snapshot_id"])
    shown = get_experiment(client, slug, line)["version_id"]
    tag(client, slug, line, ["ailleurs"])  # quelqu'un d'autre a écrit entre-temps
    refused = [
        post_entry(client, slug, line, if_match=shown, title="x", snapshot_id=snap["snapshot_id"], component="table"),
        patch_entry(client, slug, line, entry["id"], if_match=shown, note="x"),
        delete_entry(client, slug, line, entry["id"], if_match=shown),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [(412, "stale_version")] * 3
    assert entries(client, slug, line) == [entry]
    current = get_experiment(client, slug, line)["version_id"]
    assert update_entry(client, slug, line, entry["id"], if_match=current, note="à jour")["note"] == "à jour"


def test_viewers_read_the_notebook_but_do_not_change_it(client, demo_data):
    signup(client, "admin@example.com")  # le premier compte est admin : il a accès à tout µprojet
    signup(client, "viewer-nb@example.com", name="V")
    slug, line = _setup(client, "owner-nb@example.com")
    snap = take_snapshot(client, slug)
    entry = add_entry(client, slug, line, snap["snapshot_id"])
    add_member(client, slug, "viewer-nb@example.com", "viewer")
    login(client, "viewer-nb@example.com")
    assert get_snapshot(client, slug, snap["snapshot_id"]).status_code == 200
    assert entries(client, slug, line) == [entry]
    assert post_snapshot(client, slug).status_code == 403
    assert post_entry(client, slug, line, title="Vue", snapshot_id=snap["snapshot_id"], component="table").status_code == 403
    assert patch_entry(client, slug, line, entry["id"], note="x").status_code == 403
    assert delete_entry(client, slug, line, entry["id"]).status_code == 403


def test_a_member_of_another_microproject_reads_nothing(client, demo_data):
    slug, line = _setup(client, "owner-nb2@example.com")
    snap = take_snapshot(client, slug)
    signup_with_microproject(client, "other-nb@example.com", "Ailleurs")
    assert get_snapshot(client, slug, snap["snapshot_id"]).status_code == 403
    assert client.get(f"/api/microprojects/{slug}/experiments/{line}/notebook-entries").status_code == 403
