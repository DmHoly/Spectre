"""Les entrées manuelles du cahier (ex-preuves) : ce que PRISM ne prévoit pas - une valeur, un texte,
un tableau collé, des fichiers (images annotées, documents) et des liens -, validé et borné par le
serveur. Et, pour les deux types d'entrée, leur place dans le procédé et sur les plaques : une
mesure par étape (``step_id``), une même mesure faite à plusieurs étapes dans une seule entrée, la
donnée qui suit la plaque d'une version à l'autre, l'étape retirée, le décompte par étape, et la
conclusion qui cite des entrées."""

from __future__ import annotations

import pytest

from support.experiments import conclude, evolve, get_experiment, launch, step_ids, track_entities, versions
from support.http import PNG_1PX
from support.microprojects import create_microproject, signup_with_microproject
from support.notebook import (
    add_entry,
    add_manual,
    as_input,
    delete_entry,
    entries,
    entries_url,
    patch_entry,
    post_entry,
    step_counts,
    take_snapshot,
    update_entry,
    upload_notebook_file,
)
from support.structures import deposition, etch, fixed_step_id, identified


def _manual(**measurement):
    return {"kind": "manual", "title": "Mesure", "measurements": [measurement]}


def test_a_manual_entry_carries_a_value_a_text_a_table_files_and_links(client):
    slug = signup_with_microproject(client, "manual@example.com", name="Ada")
    launched = launch(client, slug, objectives=[{"name": "Rugosité", "metric": "rms", "direction": "minimize"}])
    image = upload_notebook_file(client, slug, "afm.png")
    pdf = upload_notebook_file(client, slug, "rapport.pdf", content=b"%PDF-1.4", content_type="application/pdf")
    response = post_entry(
        client,
        slug,
        launched["id"],
        kind="manual",
        title="  AFM après épitaxie  ",
        note="Mesure faite au labo.",
        objective="Rugosité",
        interpretation="Rugosité en baisse",
        wafers=["w1"],
        measurements=[
            {
                "step_id": fixed_step_id(1),
                "value": {"number": 1.2, "unit": "nm", "name": "rugosite_rms"},
                "text": "  Quelques dislocations.  ",
                "table": {"columns": ["Point", "RMS (nm)"], "rows": [["centre", 1.1], ["bord", 1.4], ["coin", None]]},
                "attachments": [{"id": image, "caption": " Vue d'ensemble "}, pdf],
                "links": [{"url": "https://aledia.sharepoint.com/sites/rd/W1", "label": "Revue du run"}, {"url": "http://intranet/afm"}],
                "annotations": [{"attachment_id": image, "type": "box", "x": 10, "y": 20, "x2": 30, "y2": 40, "label": "défaut"}],
            }
        ],
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert response.headers["Location"] == f"{entries_url(slug, launched['id'])}/{entry['id']}"
    assert entry["id"].startswith("nb_") and entry["kind"] == "manual"
    assert (entry["title"], entry["note"], entry["objective"], entry["interpretation"]) == ("AFM après épitaxie", "Mesure faite au labo.", "Rugosité", "Rugosité en baisse")
    assert entry["wafers"] == ["W1"] and entry["applies"] is True  # une clé de wafer : sans casse ni séparateur
    assert (entry["created_by"], entry["updated_by"]) == ("Ada", "Ada") and entry["created_at"] == entry["updated_at"]
    [measurement] = entry["measurements"]
    assert measurement["step_id"] == fixed_step_id(1) and measurement["step_retired"] is False
    assert measurement["value"] == {"number": 1.2, "unit": "nm", "name": "rugosite_rms"}
    assert measurement["text"] == "Quelques dislocations."
    assert measurement["table"] == {"columns": ["Point", "RMS (nm)"], "rows": [["centre", 1.1], ["bord", 1.4], ["coin", None]]}
    assert [(a["id"], a["filename"], a["content_type"], a["caption"]) for a in measurement["attachments"]] == [
        (image, "afm.png", "image/png", "Vue d'ensemble"),
        (pdf, "rapport.pdf", "application/pdf", None),
    ]
    assert measurement["links"] == [{"label": "Revue du run", "url": "https://aledia.sharepoint.com/sites/rd/W1"}, {"label": None, "url": "http://intranet/afm"}]
    assert measurement["annotations"] == [{"attachment_id": image, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut"}]
    # les fichiers arrivent avec leur url : une image s'affiche, un document se télécharge
    shown, download = (client.get(a["url"]) for a in measurement["attachments"])
    assert shown.content == PNG_1PX and "attachment" not in shown.headers.get("content-disposition", "")
    assert download.content == b"%PDF-1.4" and download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert get_experiment(client, slug, launched["id"])["notebook_count"] == 1


def test_an_empty_manual_measurement_marks_the_step_where_it_was_made(client):
    slug = signup_with_microproject(client, "manual-empty@example.com")
    launched = launch(client, slug)
    entry = add_manual(client, slug, launched["id"], "Coupe SEM faite", measurements=[{"step_id": fixed_step_id(1)}])
    [measurement] = entry["measurements"]
    assert (measurement["value"], measurement["text"], measurement["table"], measurement["attachments"], measurement["links"]) == (None, None, None, [], [])
    # une entrée manuelle peut même n'avoir aucune mesure : une observation non située
    assert add_manual(client, slug, launched["id"], "Observation", measurements=[])["measurements"] == []


def test_links_are_web_addresses_only(client):
    slug = signup_with_microproject(client, "manual-links@example.com")
    line = launch(client, slug)["id"]
    for url in ("javascript:alert(1)", "\\\\srv-data\\R&D\\Runs", "S:\\Mesures", "ftp://serveur/x", "https://", "data:text/html,x", "https://a b.fr", ""):
        response = post_entry(client, slug, line, **_manual(links=[{"url": url}]))
        assert response.status_code == 422 and response.json()["code"] == "invalid_link", url
    too_many = [{"url": f"https://exemple.fr/{i}"} for i in range(11)]
    assert post_entry(client, slug, line, **_manual(links=too_many)).status_code == 422
    # des doublons ne comptent qu'une fois
    entry = add_manual(client, slug, line, measurements=[{"links": [{"url": "https://exemple.fr"}, {"url": "https://exemple.fr", "label": "x"}]}])
    assert [link["url"] for link in entry["measurements"][0]["links"]] == ["https://exemple.fr"]
    assert get_experiment(client, slug, line)["notebook_count"] == 1  # rien d'écrit pour les refus


def test_a_pasted_table_is_validated_and_bounded(client):
    slug = signup_with_microproject(client, "manual-table@example.com")
    line = launch(client, slug)["id"]
    refused = {
        "pas de colonne": {"columns": [], "rows": []},
        "trop de colonnes": {"columns": [f"c{i}" for i in range(51)], "rows": []},
        "ligne trop courte": {"columns": ["a", "b"], "rows": [["1"]]},
        "ligne trop longue": {"columns": ["a"], "rows": [["1", "2"]]},
        "trop de lignes": {"columns": ["a"], "rows": [[i] for i in range(1001)]},
        "cellule trop longue": {"columns": ["a"], "rows": [["x" * 501]]},
        "colonne trop longue": {"columns": ["x" * 501], "rows": []},
    }
    for reason, table in refused.items():
        response = post_entry(client, slug, line, **_manual(table=table))
        assert response.status_code == 422, reason
        assert response.json()["code"] == "invalid_table", reason
    # une cellule est un texte, un nombre, un booléen ou vide - pas une structure
    assert post_entry(client, slug, line, **_manual(table={"columns": ["a"], "rows": [[{"x": 1}]]})).status_code == 422
    table = {"columns": ["a", "b", "c"], "rows": [["x", 1, True], [None, 2.5, False]]}
    assert add_manual(client, slug, line, measurements=[{"table": table}])["measurements"][0]["table"] == table


def test_a_value_is_a_finite_number(client):
    slug = signup_with_microproject(client, "manual-value@example.com")
    line = launch(client, slug)["id"]
    assert post_entry(client, slug, line, **_manual(value={"number": "beaucoup"})).status_code == 422
    assert post_entry(client, slug, line, **_manual(value={"unit": "nm"})).status_code == 422
    infinite = client.post(entries_url(slug, line), content=b'{"kind": "manual", "title": "x", "measurements": [{"value": {"number": Infinity}}]}', headers={"Content-Type": "application/json"})
    assert infinite.status_code == 422
    entry = add_manual(client, slug, line, measurements=[{"value": {"number": 3, "unit": " nm "}}])
    assert entry["measurements"][0]["value"] == {"number": 3.0, "unit": "nm", "name": None}


def test_files_must_be_uploaded_to_this_microproject_and_annotations_target_its_images(client):
    slug = signup_with_microproject(client, "manual-files@example.com")
    elsewhere = create_microproject(client, "Ailleurs")["slug"]
    line = launch(client, slug)["id"]
    image = upload_notebook_file(client, slug)
    pdf = upload_notebook_file(client, slug, "r.pdf", content=b"%PDF", content_type="application/pdf")
    for attachments in (
        ["att_" + "0" * 20],  # jamais téléversé
        ["../secret"],  # pas un id
        [upload_notebook_file(client, elsewhere)],  # téléversé dans un autre µprojet
        [image, image],  # deux fois le même
        [upload_notebook_file(client, slug, f"{i}.png") for i in range(13)],  # trop
    ):
        assert post_entry(client, slug, line, **_manual(attachments=attachments)).status_code == 422, attachments
    box = {"type": "box", "x": 1, "y": 1}
    # une annotation se pose sur une image de la mesure, pas sur un document ni sur une image d'ailleurs
    assert post_entry(client, slug, line, **_manual(attachments=[pdf], annotations=[{"attachment_id": pdf, **box}])).status_code == 422
    assert post_entry(client, slug, line, **_manual(attachments=[pdf], annotations=[{"attachment_id": image, **box}])).status_code == 422
    assert post_entry(client, slug, line, **_manual(attachments=[image], annotations=[{"attachment_id": image, "type": "cercle", "x": 1, "y": 1}])).status_code == 422
    assert len(versions(client, slug, line)) == 1  # rien d'écrit


def test_a_manual_measurement_has_no_snapshot_and_a_prism_one_no_manual_content(client):
    slug = signup_with_microproject(client, "manual-kinds@example.com")
    line = launch(client, slug)["id"]
    assert post_entry(client, slug, line, **_manual(snapshot_id="snap_" + "0" * 20)).status_code == 422
    assert post_entry(client, slug, line, **_manual(component="table")).status_code == 422
    assert post_entry(client, slug, line, kind="prism", title="x", measurements=[{"value": {"number": 1}}]).status_code == 422


def test_annotations_are_edited_by_replacing_the_measurements(client):
    slug = signup_with_microproject(client, "manual-annotate@example.com")
    line = launch(client, slug)["id"]
    image = upload_notebook_file(client, slug, "sem.png")
    entry = add_manual(client, slug, line, "SEM du bord", measurements=[{"attachments": [image]}])
    shown = get_experiment(client, slug, line)["version_id"]
    [measurement] = entry["measurements"]
    annotations = [
        {"attachment_id": image, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut ici"},
        {"attachment_id": image, "type": "arrow", "x": 5.0, "y": 5.0, "x2": 15.0, "y2": 15.0, "label": None},
    ]
    response = patch_entry(client, slug, line, entry["id"], if_match=shown, measurements=[{**as_input(measurement), "annotations": annotations}])
    assert response.status_code == 200, response.text
    annotated = response.json()
    assert [a["label"] for a in annotated["measurements"][0]["annotations"]] == ["défaut ici", None]
    assert [a["id"] for a in annotated["measurements"][0]["attachments"]] == [image]
    after = get_experiment(client, slug, line)["version_id"]
    assert after != shown and response.headers["ETag"] == f'"{after}"'
    assert annotated["updated_at"] >= entry["updated_at"]

    # les mêmes annotations : 200, et pas de nouvelle version
    count = len(versions(client, slug, line))
    again = update_entry(client, slug, line, entry["id"], if_match=after, measurements=[as_input(m) for m in annotated["measurements"]])
    assert again == annotated
    assert len(versions(client, slug, line)) == count


# -- les étapes du procédé et les plaques -----------------------------------------------------------


def _epitaxy_line(client, slug):
    """Une piste d'une seule étape (l'épitaxie, ``fixed_step_id(1)``), suivie sur la plaque W1."""
    return launch(client, slug, title="Épitaxie", steps=identified([deposition("Épitaxie GaN", "GaN", thickness_nm=200)]), entities=[{"sample_id": "W1"}])


def _with_contacts():
    """Le procédé suivant : l'épitaxie (même id), puis un etch back et des contacts (ids neufs)."""
    return [
        {"id": fixed_step_id(1), **deposition("Épitaxie GaN", "GaN", thickness_nm=200)},
        etch("Etch back", depth_nm=50),
        deposition("Contacts", "Ti", thickness_nm=30),
    ]


def test_data_follows_the_plate_across_versions(client):
    """Décision du 2026-10-04 : une mesure d'épitaxie sur W1 reste valable quand on ajoute un etch
    back puis des contacts, tant que la piste suit W1 ; une autre plaque, elle, ne la reprend pas."""
    slug = signup_with_microproject(client, "follows-plate@example.com")
    line = _epitaxy_line(client, slug)["id"]
    epitaxy = add_manual(client, slug, line, "PL après épitaxie", wafers=["W1"], measurements=[{"step_id": fixed_step_id(1), "value": {"number": 365, "unit": "nm"}}])
    whole_line = add_manual(client, slug, line, "Note de la piste", measurements=[])

    evolve(client, slug, line, steps=_with_contacts())
    ids = step_ids(client, slug, line)
    assert ids[0] == fixed_step_id(1) and len(ids) == 3
    [carried] = entries(client, slug, line, step=fixed_step_id(1))
    assert carried["id"] == epitaxy["id"] and carried["applies"] is True
    assert carried["measurements"][0]["step_retired"] is False
    assert step_counts(client, slug, line) == {fixed_step_id(1): 1}

    # la piste suit désormais une autre plaque : la mesure de W1 reste au cahier, sans s'appliquer
    track_entities(client, slug, line, [{"sample_id": "W2"}])
    shown = {entry["id"]: entry["applies"] for entry in entries(client, slug, line)}
    assert shown == {epitaxy["id"]: False, whole_line["id"]: True}  # « toute la piste » vaut pour W2 aussi
    assert step_counts(client, slug, line) == {}
    assert [entry["id"] for entry in entries(client, slug, line, wafer="w-1")] == [epitaxy["id"], whole_line["id"]]
    assert [entry["id"] for entry in entries(client, slug, line, wafer="W2")] == [whole_line["id"]]
    # une plaque que la version ne suit pas ne se cite pas à l'écriture - sauf si l'entrée la portait déjà
    refused = post_entry(client, slug, line, kind="manual", title="x", wafers=["W1"], measurements=[])
    assert refused.status_code == 422 and refused.json()["code"] == "unknown_wafer"
    assert update_entry(client, slug, line, epitaxy["id"], wafers=["W1"], note="mesure d'avant")["wafers"] == ["W1"]


def test_one_entry_compares_the_same_measurement_at_several_steps(client, demo_data):
    slug = signup_with_microproject(client, "multi-steps@example.com")
    line = _epitaxy_line(client, slug)["id"]
    evolve(client, slug, line, steps=_with_contacts())
    epitaxy, etch_back, contacts = step_ids(client, slug, line)
    entry = add_manual(
        client,
        slug,
        line,
        "Épaisseur",
        wafers=["W1"],
        measurements=[
            {"step_id": epitaxy, "value": {"number": 200, "unit": "nm"}},
            {"step_id": contacts, "value": {"number": 150, "unit": "nm"}},
        ],
    )
    assert [m["step_id"] for m in entry["measurements"]] == [epitaxy, contacts]
    assert step_counts(client, slug, line) == {epitaxy: 1, contacts: 1}
    assert [e["id"] for e in entries(client, slug, line, step=contacts)] == [entry["id"]]
    assert entries(client, slug, line, step=etch_back) == []
    # une seule mesure par étape, et une étape du procédé de la version
    twice = post_entry(client, slug, line, kind="manual", title="x", measurements=[{"step_id": epitaxy}, {"step_id": epitaxy}])
    assert twice.status_code == 422
    unknown = post_entry(client, slug, line, kind="manual", title="x", measurements=[{"step_id": "st_ffffffff"}])
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_step"
    # une vue PRISM se situe aussi dans le procédé
    view = add_entry(client, slug, line, take_snapshot(client, slug, wafers=["W1"])["snapshot_id"], step_id=etch_back)
    assert step_counts(client, slug, line) == {epitaxy: 1, etch_back: 1, contacts: 1}
    assert step_counts(client, slug, line, kind="prism") == {etch_back: 1}
    assert [e["id"] for e in entries(client, slug, line, kind="prism")] == [view["id"]]


@pytest.fixture()
def demo_data(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


def test_a_measurement_whose_step_left_the_process_is_kept_and_marked(client, demo_data):
    slug = signup_with_microproject(client, "retired-step@example.com")
    line = _epitaxy_line(client, slug)["id"]
    evolve(client, slug, line, steps=_with_contacts())
    epitaxy, etch_back, contacts = step_ids(client, slug, line)
    entry = add_manual(client, slug, line, "Profil", measurements=[{"step_id": etch_back, "text": "50 nm"}, {"step_id": contacts, "text": "ok"}])
    before = get_experiment(client, slug, line)["version_id"]

    # une évolution retire l'etch back
    evolve(client, slug, line, steps=[_with_contacts()[0], {"id": contacts, **deposition("Contacts", "Ti", thickness_nm=30)}])
    assert step_ids(client, slug, line) == [epitaxy, contacts]
    [kept] = entries(client, slug, line)
    assert [(m["step_id"], m["step_retired"]) for m in kept["measurements"]] == [(etch_back, True), (contacts, False)]
    # la version d'avant, elle, avait l'étape
    [old] = entries(client, slug, line, version=before)
    assert [m["step_retired"] for m in old["measurements"]] == [False, False]
    # l'étape retirée reste citée quand on renvoie les mesures ; on ne peut plus y ajouter une mesure
    texts = update_entry(client, slug, line, entry["id"], measurements=[{**as_input(m), "text": m["text"] + " !"} for m in kept["measurements"]])
    assert [m["text"] for m in texts["measurements"]] == ["50 nm !", "ok !"]
    retired = post_entry(client, slug, line, kind="manual", title="x", measurements=[{"step_id": etch_back}])
    assert retired.status_code == 422 and retired.json()["code"] == "unknown_step"


def test_the_conclusion_cites_notebook_entries(client):
    slug = signup_with_microproject(client, "cites@example.com")
    line = launch(client, slug, objectives=[{"name": "Rugosité", "metric": "rms", "direction": "minimize"}])["id"]
    entry = add_manual(client, slug, line, "AFM", objective="Rugosité", measurements=[{"value": {"number": 1.2, "unit": "nm"}}])
    other = add_manual(client, slug, line, "Autre")
    result = {"objective": "Rugosité", "status": "met", "evidence_ids": [entry["id"], other["id"]]}
    concluded = conclude(client, slug, line, objective_results=[result])
    assert concluded["conclusion"]["objective_results"][0]["evidence_ids"] == [entry["id"], other["id"]]
    unknown = client.put(f"/api/microprojects/{slug}/experiments/{line}/conclusion", json={"status": "concluded", "objective_results": [{**result, "evidence_ids": ["nb_inconnue"]}]})
    assert unknown.status_code == 422 and unknown.json()["code"] == "notebook_entry_not_found"
    # retirer une entrée citée la retire des verdicts ; la conclusion reste conclue
    assert delete_entry(client, slug, line, other["id"]).status_code == 204
    after = get_experiment(client, slug, line)
    assert after["conclusion"]["objective_results"][0]["evidence_ids"] == [entry["id"]]
    assert after["status"] == "concluded"
