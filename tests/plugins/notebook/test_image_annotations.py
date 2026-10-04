"""Les annotations des images du cahier : une flèche ou un cadre (la forme du noyau,
``spectre.kernel.annotations``) se pose sur toute image d'une mesure - un fichier téléversé
(``attachment_id``) comme une image externe (``external_image``, son chemin). La clé d'une image ne
dépend pas de sa place : réordonner les images garde leurs annotations. Poser ou retirer une
annotation est une écriture du cahier, jamais un changement de structure."""

from __future__ import annotations

import json

import pytest

from support.experiments import get_experiment, launch, versions
from support.external_images import png_files
from support.microprojects import join_as, signup_with_microproject
from support.notebook import add_manual, as_input, entries_by_id, patch_entry, update_entry, upload_notebook_file

BOX = {"type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut"}
ARROW = {"type": "arrow", "x": 5.0, "y": 5.0, "x2": 50.0, "y2": 60.0, "label": None}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    allowed = tmp_path / "mesures"
    allowed.mkdir()
    monkeypatch.setenv("SPECTRE_EXTERNAL_IMAGE_ROOTS", str(allowed))
    return allowed


def _structural(client, slug, line):
    return [(v["version"], v["change_level"]) for v in versions(client, slug, line) if v["change_level"] != "none"]


def test_an_external_image_is_annotated_by_its_path_and_keeps_its_annotations_when_reordered(client, root):
    slug = signup_with_microproject(client, "annot-ext@example.com", "Coupes")
    line = launch(client, slug)["id"]
    first, second = png_files(root, "tem-1.png", "tem-2.png")
    entry = add_manual(client, slug, line, "Coupe TEM", measurements=[{"external_images": [{"path": first}, {"path": second}]}])
    [measurement] = entry["measurements"]
    structural = _structural(client, slug, line)

    # une flèche sur la seconde image, un cadre sur la première
    annotations = [{"external_image": second, **ARROW}, {"external_image": first, **BOX, "label": "  puits  "}]
    annotated = update_entry(client, slug, line, entry["id"], measurements=[{**as_input(measurement), "annotations": annotations}])
    stored = annotated["measurements"][0]["annotations"]
    assert stored == [{"external_image": second, **ARROW}, {"external_image": first, **BOX, "label": "puits"}]
    assert entries_by_id(client, slug, line)[entry["id"]]["measurements"][0]["annotations"] == stored

    # les images réordonnées (leur rang et leur url changent) : chaque annotation reste sur son image
    reordered = update_entry(
        client, slug, line, entry["id"], measurements=[{"external_images": [{"path": second}, {"path": first}], "annotations": stored}]
    )
    [after] = reordered["measurements"]
    assert [(i["index"], i["path"]) for i in after["external_images"]] == [(0, second), (1, first)]
    assert after["annotations"] == stored

    # retirer une annotation ; puis l'image annotée, avec ce qui la désigne encore
    kept = update_entry(client, slug, line, entry["id"], measurements=[{**as_input(after), "annotations": [stored[0]]}])
    assert kept["measurements"][0]["annotations"] == [stored[0]]
    without_second = update_entry(client, slug, line, entry["id"], measurements=[{"external_images": [{"path": first}], "annotations": []}])
    assert without_second["measurements"][0]["annotations"] == []
    # des annotations : aucune version de structure
    assert _structural(client, slug, line) == structural


def test_an_annotation_targets_an_image_of_its_measurement(client, root):
    slug = signup_with_microproject(client, "annot-target@example.com", "Coupes")
    line = launch(client, slug)["id"]
    inside, other = png_files(root, "tem.png", "autre.png")
    image = upload_notebook_file(client, slug, "sem.png")
    entry = add_manual(client, slug, line, measurements=[{"attachments": [image], "external_images": [{"path": inside}]}])
    measurement = as_input(entry["measurements"][0])
    count = len(versions(client, slug, line))

    refused = [
        [{"external_image": other, **BOX}],  # une image externe qui n'est pas dans la mesure
        [{**BOX}],  # aucune image désignée
        [{"attachment_id": image, "external_image": inside, **BOX}],  # deux à la fois
        [{"external_image": inside, **BOX, "x": float("inf")}],
        [{"external_image": inside, **BOX, "x2": 100.01}],  # hors de l'image (en % : entre 0 et 100)
        [{"external_image": inside, **BOX}] * 101,
    ]
    for annotations in refused:
        response = client.patch(
            f"/api/microprojects/{slug}/experiments/{line}/notebook-entries/{entry['id']}",
            content=json.dumps({"measurements": [{**measurement, "annotations": annotations}]}, allow_nan=True),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, annotations
    assert len(versions(client, slug, line)) == count  # rien d'écrit

    # un fichier et une image externe de la même mesure, annotés ensemble
    both = update_entry(
        client, slug, line, entry["id"], measurements=[{**measurement, "annotations": [{"attachment_id": image, **ARROW}, {"external_image": inside, **BOX}]}]
    )
    assert both["measurements"][0]["annotations"] == [{"attachment_id": image, **ARROW}, {"external_image": inside, **BOX}]


def test_a_viewer_reads_the_annotations_an_editor_writes(client, root):
    slug = signup_with_microproject(client, "annot-owner@example.com", "Coupes")
    line = launch(client, slug)["id"]
    [path] = png_files(root, "tem.png")
    entry = add_manual(client, slug, line, measurements=[{"external_images": [{"path": path}]}])
    annotated = update_entry(client, slug, line, entry["id"], measurements=[{"external_images": [{"path": path}], "annotations": [{"external_image": path, **BOX}]}])

    join_as(client, slug, "annot-viewer@example.com", owner="annot-owner@example.com", role="viewer")
    assert entries_by_id(client, slug, line)[entry["id"]]["measurements"][0]["annotations"] == annotated["measurements"][0]["annotations"]
    tip = get_experiment(client, slug, line)["version_id"]
    response = patch_entry(client, slug, line, entry["id"], if_match=tip, measurements=[{"external_images": [{"path": path}], "annotations": []}])
    assert response.status_code == 403

    join_as(client, slug, "annot-editor@example.com", owner="annot-owner@example.com", role="editor")
    response = patch_entry(client, slug, line, entry["id"], if_match=tip, measurements=[{"external_images": [{"path": path}], "annotations": []}])
    assert response.status_code == 200 and response.json()["measurements"][0]["annotations"] == []
