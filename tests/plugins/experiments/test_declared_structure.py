"""Expérience sans structure (spectre.plugins.structures.kinds.DeclaredStructure) : lancée sans
constructeur ni image obligatoire - une description, un dessin collé si l'on veut, et le split
déclaré dans un tableau, une ligne par plaque. Le reste (plaques, FDL, cahier, conclusion, versions)
marche comme pour les autres études."""

from __future__ import annotations

from support.experiments import (
    conclude,
    evolve,
    experiment_url,
    get_experiment,
    launch_body,
    launch_declared,
    lineage,
    post_evolve,
    structure_history,
    track_entities,
    versions,
)
from support.http import assert_handler_404
from support.microprojects import signup_with_microproject
from support.structures import upload_structure_image
from support.wafers import get_wafer

from spectre.plugins.structures.kinds import DECLARED_STRUCTURE_KEY, KINDS, DeclaredStructure


def _microproject(client):
    return signup_with_microproject(client, "declare@example.com", "Contacts")


def _post(client, slug, **structure):
    body = launch_body(kind="declared", title="Recuit", intent="Voir", entities=[], **structure)
    return client.post(f"/api/microprojects/{slug}/experiments", json=body)


def _structural(client, slug, ref):
    return [(v["version"], v["change_level"]) for v in versions(client, slug, ref) if v["change_level"] != "none"]


def test_the_registry_key_is_frozen():
    assert DECLARED_STRUCTURE_KEY == "spectre.structures.DeclaredStructure"
    assert DeclaredStructure.registry_key() == DECLARED_STRUCTURE_KEY
    assert KINDS[DECLARED_STRUCTURE_KEY].entity_count({"wafers": [{"values": []}, {"values": []}]}) == 2


def test_launch_without_structure_tracks_one_wafer_per_row(client):
    slug = _microproject(client)
    detail = launch_declared(
        client,
        slug,
        factors=["Recuit", " Dopage Mg "],
        wafers=[
            {"label": " réf ", "values": ["600 °C", "2e19"]},
            {"values": ["650 °C", "2e19"]},
            {"values": ["", ""]},
        ],
        entities=[{"sample_id": "W1"}, {"sample_id": None}, {"sample_id": "W3", "fdl": ["FDL-12"]}],
        description="  Contact P Ni/Au sur GaN:Mg, la réf = procédé standard  ",
    )
    assert detail["structure_kind"] == "declared"
    assert detail["structure_svg"] is None and detail["is_batch"] is False and detail["structure_images"] is None
    assert detail["has_editable_process"] is False
    assert detail["declared_structure"] == {
        "description": "Contact P Ni/Au sur GaN:Mg, la réf = procédé standard",
        "images": [],
        "factors": ["Recuit", "Dopage Mg"],
        "wafers": [
            {"label": "réf", "values": ["600 °C", "2e19"], "name": "réf"},
            {"label": None, "values": ["650 °C", "2e19"], "name": "Recuit = 650 °C · Dopage Mg = 2e19"},
            {"label": None, "values": ["", ""], "name": "Plaque 3"},
        ],
    }
    # une place par ligne, à sa place
    assert [e["sample_id"] for e in detail["physical_tracking"]] == ["W1", None, "W3"]
    assert detail["physical_tracking"][2]["fdl"] == ["FDL-12"]
    assert_handler_404(client.get(f"{experiment_url(slug, detail['id'])}/process"), "procédé éditable")
    assert _structural(client, slug, detail["id"]) == [("1.0.0", "initial")]

    # les plaques nommées se retrouvent dans la liste des plaques, sous le nom de leur ligne
    passport = get_wafer(client, "W3")
    assert passport["occurrences"][0]["entity_index"] == 2 and passport["occurrences"][0]["variant"] == "Plaque 3"


def test_the_minimum_is_a_title_an_intent_and_one_row(client):
    slug = _microproject(client)
    # ni description, ni dessin, ni colonne : une ligne suffit
    minimal = _post(client, slug, wafers=[{}])
    assert minimal.status_code == 201, minimal.text
    assert minimal.json()["declared_structure"]["wafers"] == [{"label": None, "values": [], "name": "Plaque 1"}]
    assert minimal.json()["physical_tracking"] == [{"sample_id": None, "location": None}]

    assert _post(client, slug, wafers=[]).json()["code"] == "declared_no_wafer"
    assert _post(client, slug, factors=["  "], wafers=[{"values": ["x"]}]).json()["code"] == "declared_factor_unnamed"
    assert _post(client, slug, factors=["Recuit", "recuit"], wafers=[{"values": ["a", "b"]}]).json()["code"] == "declared_factor_duplicate"
    assert _post(client, slug, factors=["Recuit"], wafers=[{"values": []}]).json()["code"] == "declared_values_mismatch"
    too_many = client.post(
        f"/api/microprojects/{slug}/experiments",
        json=launch_body(kind="declared", entities=[{"sample_id": "A"}, {"sample_id": "B"}], wafers=[{}]),
    )
    assert too_many.status_code == 422 and too_many.json()["code"] == "too_many_entities"


def test_a_pasted_drawing_is_optional_and_must_be_an_uploaded_image(client):
    slug = _microproject(client)
    image_id = upload_structure_image(client, slug, "dessin.png")
    detail = launch_declared(client, slug, images=[{"image_id": image_id, "kind": "schema", "caption": " le dessin "}])
    image = detail["declared_structure"]["images"][0]
    assert image["image_id"] == image_id and image["caption"] == "le dessin"
    assert client.get(image["url"]).status_code == 200
    assert _post(client, slug, wafers=[{}], images=[{"image_id": "nope"}]).status_code in (404, 422)


def test_editing_the_split_is_a_new_structure_version_and_keeps_wafers_in_place(client):
    slug = _microproject(client)
    launched = launch_declared(client, slug, entities=[{"sample_id": "W1"}, {"sample_id": "W2"}])
    ref = launched["id"]
    conclude(client, slug, ref, summary="ok")

    # l'intention seule change : même structure, la conclusion reste
    same = evolve(
        client, slug, ref, kind="declared", description="Contact P sur GaN", factors=["Recuit"],
        wafers=[{"label": "réf", "values": ["standard"]}, {"values": ["long"]}], title="Recuit bis",
    )
    assert same["conclusion"]["summary"] == "ok"
    assert [e["sample_id"] for e in same["physical_tracking"]] == ["W1", "W2"]

    # une ligne de plus : une nouvelle structure, la nouvelle ligne est à associer
    grown = evolve(
        client, slug, ref, kind="declared", factors=["Recuit"],
        wafers=[{"label": "réf", "values": ["standard"]}, {"values": ["long"]}, {"values": ["très long"]}],
    )
    assert grown["conclusion"]["summary"] in (None, "")
    assert [e["sample_id"] for e in grown["physical_tracking"]] == ["W1", "W2", None]
    assert [w["name"] for w in grown["declared_structure"]["wafers"]] == ["réf", "Recuit = long", "Recuit = très long"]
    assert _structural(client, slug, ref) == [("1.0.0", "initial"), ("2.0.0", "major")]

    # une ligne de moins alors que ses deux plaques sont nommées : refusé
    shrink = post_evolve(client, slug, ref, kind="declared", title="t", intent="i", wafers=[{}])
    assert shrink.status_code == 422 and shrink.json()["code"] == "too_many_entities"


def test_a_declared_study_can_be_continued_in_the_builder(client):
    slug = _microproject(client)
    ref = launch_declared(client, slug, entities=[{"sample_id": "W1"}, {}])["id"]
    drawn = evolve(client, slug, ref)  # le procédé par défaut du support
    assert drawn["structure_kind"] == "process" and drawn["declared_structure"] is None
    assert drawn["has_editable_process"] is True
    assert [e["sample_id"] for e in drawn["physical_tracking"]] == ["W1"]


def test_the_lineage_tells_a_declared_study_apart(client):
    slug = _microproject(client)
    ref = launch_declared(client, slug)["id"]
    nodes = structure_history(client, slug)["nodes"]
    assert [n["structure_kind"] for n in nodes] == ["declared"]
    assert lineage(client, slug)["nodes"]
    assert get_experiment(client, slug, ref)["ref_names"]


def test_the_plates_card_keeps_one_place_per_row(client):
    slug = _microproject(client)
    ref = launch_declared(client, slug)["id"]  # deux lignes
    named = track_entities(client, slug, ref, [{"sample_id": "W1"}, {"sample_id": "W2"}])
    assert [e["sample_id"] for e in named["physical_tracking"]] == ["W1", "W2"]
    for wrong in ([{"sample_id": "W1"}], [{"sample_id": "W1"}, {"sample_id": "W2"}, {"sample_id": "W3"}]):
        response = client.put(f"{experiment_url(slug, ref)}/entities", json={"entities": wrong})
        assert response.status_code == 422 and response.json()["code"] == "entity_count"
