"""Cahier de données (plugin notebook) : charger un type de données de caractérisation pour les
plaques d'une étude, le figer en instantané, et garder des vues dessus (les entrées PRISM : un
composant de visualisation + ses réglages) avec des notes - chaque changement une écriture sur la
piste, comme le reste de la fiche. Les entrées manuelles sont dans test_manual_entries.py, les
données d'avant le cahier unique dans test_legacy.py. Utilise la source de démonstration (SPECTRE_DEMO_DATA=1) : PRISM lui-même demande
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
    add_manual,
    as_input,
    delete_entry,
    entries,
    entries_url,
    get_entry,
    get_snapshot,
    patch_entry,
    post_entry,
    post_snapshot,
    prism_body,
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
        **prism_body(
            snap["snapshot_id"],
            title="EQE vs J",
            component="eqe-curves",
            options={"maxCurves": 30},
            note="  Pas d'écart pixel / non pixel.  ",
            objective="EQE identique",
        ),
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert response.headers["Location"] == f"{entries_url(slug, line)}/{entry['id']}"
    assert response.headers["ETag"] == f'"{get_experiment(client, slug, line)["version_id"]}"'
    assert entry["kind"] == "prism" and entry["title"] == "EQE vs J" and entry["note"] == "Pas d'écart pixel / non pixel."
    [measurement] = entry["measurements"]
    assert (measurement["snapshot_id"], measurement["component"], measurement["options"]) == (snap["snapshot_id"], "eqe-curves", {"maxCurves": 30})
    assert measurement["snapshot"]["hook"] == "eqe" and measurement["snapshot"]["source"] == "demo"
    assert measurement["snapshot"]["wafers"] == ["W12-A3", "W12-A4"] and measurement["step_id"] is None
    assert entry["created_by"] == "Chercheuse" and entry["in_report"] is True and entry["objective"] == "EQE identique"
    assert entry["wafers"] == [] and entry["applies"] is True
    assert entries(client, slug, line) == [entry]
    single = get_entry(client, slug, line, entry["id"])
    assert single.status_code == 200 and single.json() == entry
    # le détail de l'étude ne porte que le nombre d'entrées : le panneau lit sa propre ressource
    detail = get_experiment(client, slug, line)
    assert "data_notebook" not in detail and detail["notebook_count"] == 1

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
    assert removed.headers["ETag"] == f'"{get_experiment(client, slug, line)["version_id"]}"'
    assert [e["title"] for e in entries(client, slug, line)] == ["EQE vs J"]
    # l'historique garde chaque étape (cahier de labo), et une version passée se relit
    assert len(versions(client, slug, line)) == 6
    assert entries(client, slug, line, version=first_version) == []
    # aucune écriture du cahier ne perd l'hypothèse
    assert get_experiment(client, slug, line)["hypothesis"] == "La pixélisation ne change rien"


def test_the_list_carries_the_etag_of_the_version_read(client, demo_data):
    slug, line = _setup(client)
    first = get_experiment(client, slug, line)["version_id"]
    response = client.get(entries_url(slug, line), params={"version": first})
    assert response.status_code == 200 and response.headers["ETag"] == f'"{first}"'
    assert_handler_404(client.get(entries_url(slug, line), params={"version": "exp_0000000000000000"}))
    assert_handler_404(client.get(entries_url(slug, "piste-inconnue")))
    assert_handler_404(get_entry(client, slug, line, "nb_000000000000"), "introuvable")
    assert client.get(entries_url(slug, line), params={"kind": "autre"}).status_code == 422
    assert client.get(entries_url(slug, line), params={"summary": "autre"}).status_code == 422


def test_the_snapshot_of_a_view_is_refreshed_through_its_measurements(client, demo_data):
    slug, line = _setup(client)
    entry = add_entry(client, slug, line, take_snapshot(client, slug)["snapshot_id"], component="table")
    fresh = take_snapshot(client, slug)
    [measurement] = entry["measurements"]
    updated = update_entry(client, slug, line, entry["id"], measurements=[{**as_input(measurement), "snapshot_id": fresh["snapshot_id"], "component": "wafer-map"}])
    assert updated["measurements"][0]["snapshot_id"] == fresh["snapshot_id"]
    assert updated["measurements"][0]["component"] == "wafer-map"
    assert updated["measurements"][0]["snapshot"]["fetched_at"] == fresh["fetched_at"]


def test_a_change_without_effect_creates_no_version(client, demo_data):
    slug, line = _setup(client)
    entry = add_entry(client, slug, line, take_snapshot(client, slug)["snapshot_id"], note="Vu")
    count = len(versions(client, slug, line))
    again = update_entry(client, slug, line, entry["id"], note="Vu", title="Vue", position=0, measurements=[as_input(m) for m in entry["measurements"]])
    assert again == entry
    assert len(versions(client, slug, line)) == count


def test_an_objective_can_be_cleared(client, demo_data):
    slug, line = _setup(client)
    entry = add_entry(client, slug, line, take_snapshot(client, slug)["snapshot_id"], objective="EQE identique")
    assert update_entry(client, slug, line, entry["id"], objective="")["objective"] is None


def test_entries_are_validated(client, demo_data):
    slug, line = _setup(client)
    snap = take_snapshot(client, slug)
    base = prism_body(snap["snapshot_id"])
    view = base["measurements"][0]
    assert post_entry(client, slug, line, **{**base, "title": " "}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "kind": "autre"}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "measurements": [{**view, "snapshot_id": "snap_" + "1" * 20}]}).json()["code"] == "snapshot_not_found"
    assert post_entry(client, slug, line, **{**base, "measurements": [{**view, "component": "<script>"}]}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "objective": "inexistant"}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "measurements": [{**view, "options": {"x": "a" * 20001}}]}).status_code == 422
    # une entrée PRISM a au moins une vue, et rien d'une donnée manuelle
    assert post_entry(client, slug, line, **{**base, "measurements": []}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "measurements": [{**view, "text": "à la main"}]}).status_code == 422
    assert post_entry(client, slug, line, **{**base, "measurements": [{"step_id": None, "component": "table"}]}).status_code == 422
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
        post_entry(client, slug, line, if_match=shown, **prism_body(snap["snapshot_id"])),
        post_entry(client, slug, line, if_match=shown, kind="manual", title="x", measurements=[{"text": "x"}]),
        patch_entry(client, slug, line, entry["id"], if_match=shown, note="x"),
        delete_entry(client, slug, line, entry["id"], if_match=shown),
    ]
    assert [(r.status_code, r.json()["code"]) for r in refused] == [(412, "stale_version")] * 4
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
    assert get_entry(client, slug, line, entry["id"]).json() == entry
    assert post_snapshot(client, slug).status_code == 403
    assert post_entry(client, slug, line, **prism_body(snap["snapshot_id"])).status_code == 403
    assert post_entry(client, slug, line, kind="manual", title="x", measurements=[{"text": "x"}]).status_code == 403
    assert patch_entry(client, slug, line, entry["id"], note="x").status_code == 403
    assert delete_entry(client, slug, line, entry["id"]).status_code == 403
    login(client, "owner-nb@example.com")
    assert add_manual(client, slug, line, measurements=[{"text": "une note"}])["kind"] == "manual"  # un editor écrit


def test_a_member_of_another_microproject_reads_nothing(client, demo_data):
    slug, line = _setup(client, "owner-nb2@example.com")
    snap = take_snapshot(client, slug)
    signup_with_microproject(client, "other-nb@example.com", "Ailleurs")
    assert get_snapshot(client, slug, snap["snapshot_id"]).status_code == 403
    assert client.get(f"/api/microprojects/{slug}/experiments/{line}/notebook-entries").status_code == 403
