"""Les annotations d'une structure en images : chaque image de ``StructureImage`` porte ses flèches et
ses cadres (la forme du noyau, ``spectre.kernel.annotations``), facultatifs. Les poser est une
écriture légère (``PUT .../structure-images``, ``If-Match``), jamais une nouvelle version de
structure ; elles suivent leur image quand on réordonne la planche ; une structure enregistrée sans
elles se relit telle quelle, et une image sans annotation s'enregistre sans la clé."""

from __future__ import annotations

from spectre.plugins.experiments.repository import get_repository
from support.experiments import (
    experiment_url,
    get_experiment,
    launch_image,
    post_evolve,
    replace_structure_images,
    structure_diff,
    versions,
)
from support.microprojects import join_as, signup_with_microproject
from support.structures import upload_structure_image

BOX = {"type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "puits"}
ARROW = {"type": "arrow", "x": 5.0, "y": 5.0, "x2": 50.0, "y2": 60.0, "label": None}


def _pictured(client, email="struct-annot@example.com"):
    slug = signup_with_microproject(client, email, "Coupes")
    schema = {"image_id": upload_structure_image(client, slug, "schema.png"), "kind": "schema", "caption": None}
    tem = {"image_id": upload_structure_image(client, slug, "tem.png"), "kind": "coupe", "caption": "FIB"}
    launched = launch_image(client, slug, [schema, tem], entities=[{"sample_id": "W7"}])
    return slug, launched, schema, tem


def _levels(client, slug, line):
    return [(v["version"], v["change_level"]) for v in versions(client, slug, line)]


def test_annotations_are_a_light_write_that_follows_each_picture(client):
    slug, launched, schema, tem = _pictured(client)
    line = launched["id"]
    assert [image["annotations"] for image in launched["structure_images"]] == [[], []]

    # une flèche et un cadre sur la coupe : une version de la piste, pas de structure
    annotated = replace_structure_images(
        client, slug, line, [schema, {**tem, "annotations": [ARROW, {**BOX, "label": "  puits  "}]}], if_match=launched["version_id"]
    )
    assert annotated["version_id"] != launched["version_id"]
    assert [image["annotations"] for image in annotated["structure_images"]] == [[], [ARROW, BOX]]
    assert _levels(client, slug, line) == [("1.0.0", "initial"), ("1.0.0", "none")]
    assert structure_diff(client, slug, line, against_version=launched["version_id"])["summary"] == ["Image 2 : annotations modifiées"]

    # la planche réordonnée : les annotations restent sur la coupe
    reordered = replace_structure_images(client, slug, line, [{**tem, "annotations": [ARROW, BOX]}, schema])
    assert [(image["image_id"], image["annotations"]) for image in reordered["structure_images"]] == [(tem["image_id"], [ARROW, BOX]), (schema["image_id"], [])]

    # retirer le cadre ; les mêmes annotations renvoyées : rien d'écrit
    removed = replace_structure_images(client, slug, line, [{**tem, "annotations": [ARROW]}, schema])
    assert removed["structure_images"][0]["annotations"] == [ARROW]
    assert replace_structure_images(client, slug, line, [{**tem, "annotations": [ARROW]}, schema])["version_id"] == removed["version_id"]
    assert all(level == "none" for _, level in _levels(client, slug, line)[1:])

    # une version à la page périmée : 412, rien d'écrit
    stale = client.put(f"{experiment_url(slug, line)}/structure-images", json={"images": [tem, schema]}, headers={"If-Match": f'"{launched["version_id"]}"'})
    assert stale.status_code == 412
    assert get_experiment(client, slug, line)["version_id"] == removed["version_id"]


def test_an_evolution_that_only_changes_annotations_is_not_a_new_structure(client):
    slug, launched, schema, tem = _pictured(client, "struct-annot-evolve@example.com")
    line = launched["id"]
    body = {"title": "Coupe", "intent": "Annoter la coupe", "images": [schema, {**tem, "annotations": [BOX]}]}
    response = post_evolve(client, slug, line, kind="images", if_match=launched["version_id"], **body)
    assert response.status_code == 201, response.text
    assert response.json()["structure_images"][1]["annotations"] == [BOX]
    assert _levels(client, slug, line) == [("1.0.0", "initial"), ("1.0.0", "none")]


def test_annotations_are_checked_and_written_by_an_editor_only(client):
    slug, launched, schema, tem = _pictured(client, "struct-annot-owner@example.com")
    line = launched["id"]
    url = f"{experiment_url(slug, line)}/structure-images"
    for bad in ([{"type": "cercle", "x": 1, "y": 1}], [{**BOX, "couleur": "rouge"}], [BOX] * 101):
        assert client.put(url, json={"images": [{**schema, "annotations": bad}, tem]}).status_code == 422
    # une position hors de l'image (en % : entre 0 et 100)
    for outside in ({"x": -1e308}, {"y": 100.5}, {"x2": 5000}, {"y2": -3}):
        response = client.put(url, json={"images": [{**schema, "annotations": [{**BOX, **outside}]}, tem]})
        assert response.status_code == 422 and response.json()["code"] == "invalid_annotation", outside
    assert len(versions(client, slug, line)) == 1

    annotated = replace_structure_images(client, slug, line, [{**schema, "annotations": [BOX]}, tem])
    join_as(client, slug, "struct-annot-viewer@example.com", owner="struct-annot-owner@example.com", role="viewer")
    assert get_experiment(client, slug, line)["structure_images"][0]["annotations"] == [BOX]
    assert client.put(url, json={"images": [schema, tem]}).status_code == 403

    join_as(client, slug, "struct-annot-editor@example.com", owner="struct-annot-owner@example.com", role="editor")
    cleared = client.put(url, json={"images": [schema, tem]}, headers={"If-Match": f'"{annotated["version_id"]}"'})
    assert cleared.status_code == 200 and cleared.json()["structure_images"][0]["annotations"] == []


def test_a_picture_without_annotations_is_stored_as_before(client):
    """Une structure enregistrée avant les annotations se relit telle quelle (une liste vide), et une
    image sans annotation s'enregistre sans la clé : l'objet Follow garde la forme d'avant."""
    slug, launched, schema, tem = _pictured(client, "struct-annot-old@example.com")
    line = launched["id"]
    stored = get_repository(slug).get(launched["version_id"]).structure
    assert stored == {"images": [schema, tem]}  # la forme d'avant : aucune clé ajoutée

    annotated = replace_structure_images(client, slug, line, [schema, {**tem, "annotations": [ARROW]}])
    assert get_repository(slug).get(annotated["version_id"]).structure == {"images": [schema, {**tem, "annotations": [ARROW]}]}
    # l'ancienne version se relit, sans annotation
    old = client.get(f"{experiment_url(slug, line)}/versions/{launched['version_id']}").json()
    assert [image["annotations"] for image in old["structure_images"]] == [[], []]
