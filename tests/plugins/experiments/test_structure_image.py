"""Structure en image (spectre.plugins.structures.kinds.StructureImage): an experiment launched without the
builder, whose structure is given as pictures - a PowerPoint schematic, TEM cross-sections... one or
several, in reading order - that can be changed later (a lightweight write, same structure
version) or continued with new ones (a real evolution, new version), including to and from a
structure drawn in the builder.
"""

from __future__ import annotations

import json

from support.attachments import post_attachment
from support.experiments import (
    evolve,
    evolve_image,
    experiment_url,
    get_version,
    launch,
    launch_body,
    launch_campaign,
    lineage,
    replace_structure_images,
    structure_diff,
    tag,
    versions,
)
from support.http import PNG_1PX, assert_handler_404
from support.microprojects import join_as, signup_with_microproject
from support.structures import campaign_plan, steps, upload_structure_image


def _owner_microproject(client, email="image@example.com"):
    return signup_with_microproject(client, email, "Coupes")


def _upload(client, slug, name="schema.png", content_type="image/png", data=None):
    return post_attachment(client, slug, "structure", name, data if data is not None else PNG_1PX, content_type)


def _image(client, slug, kind="coupe", caption=None, name="schema.png"):
    return {"image_id": upload_structure_image(client, slug, name), "kind": kind, "caption": caption}


def _launch_response(client, slug, images, title="Coupe TEM", **extra):
    fields = {
        "intent": "Documenter la structure réelle",
        "hypothesis": "Le puits fait 3 nm",
        "entities": [{"sample_id": ""}, {"sample_id": "W7", "location": "boîte 3"}],
        **extra,
    }
    return client.post(f"/api/microprojects/{slug}/experiments", json=launch_body(kind="images", images=images, title=title, **fields))


def _structural_versions(client, slug, ref):
    return [(v["version"], v["change_level"]) for v in versions(client, slug, ref) if v["change_level"] != "none"]


def test_launch_an_experiment_with_several_pictures(client):
    slug = _owner_microproject(client)
    upload = _upload(client, slug)
    assert upload.status_code == 201
    image = upload.json()
    assert image["url"] == f"/api/microprojects/{slug}/attachments/{image['id']}/content"
    served = client.get(image["url"])
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"

    overview = _image(client, slug, "coupe", "  Coupe FIB du wafer W7  ")
    launched = _launch_response(client, slug, [{"image_id": image["id"], "kind": "schema"}, overview])
    assert launched.status_code == 201
    detail = launched.json()
    # chaque image porte l'url de ses octets : le front ne la construit pas
    assert detail["structure_images"] == [
        {"image_id": image["id"], "kind": "schema", "caption": None, "url": image["url"]},
        {
            "image_id": overview["image_id"],
            "kind": "coupe",
            "caption": "Coupe FIB du wafer W7",
            "url": f"/api/microprojects/{slug}/attachments/{overview['image_id']}/content",
        },
    ]
    assert client.get(detail["structure_images"][1]["url"]).status_code == 200
    assert detail["structure_svg"] is None and detail["is_batch"] is False and detail["has_editable_process"] is False
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]
    assert detail["ref_names"]  # la toute première expérience du µprojet devient sa première ref
    # pas de procédé éditable : la fiche n'a rien à rouvrir dans le constructeur
    assert_handler_404(client.get(f"{experiment_url(slug, detail['id'])}/process"), "procédé éditable")
    assert _structural_versions(client, slug, detail["id"]) == [("1.0.0", "initial")]


def test_launch_requires_uploaded_images_a_sample_and_an_intention(client):
    slug = _owner_microproject(client)
    good = _image(client, slug)

    assert _launch_response(client, slug, []).status_code == 422
    assert _launch_response(client, slug, [{"image_id": "att_" + "0" * 20}]).status_code == 422  # jamais envoyée
    assert _launch_response(client, slug, [good, {"image_id": "../../secret"}]).status_code == 422
    assert _launch_response(client, slug, [good, good]).status_code == 422  # deux fois la même
    too_many = [_image(client, slug) for _ in range(13)]
    assert _launch_response(client, slug, too_many).status_code == 422
    no_sample = _launch_response(client, slug, [good], entities=[{"sample_id": " "}])
    assert no_sample.status_code == 422 and "entité physique" in no_sample.json()["detail"]
    assert _launch_response(client, slug, [good], intent="  ").status_code == 422

    # un fichier non image (un CSV des anciennes pièces jointes d'une expérience) ne peut pas servir
    # d'image de structure
    from spectre.plugins.attachments import store

    csv = store.new_attachment_id()
    directory = store.attachments_dir(slug)
    (directory / csv).write_bytes(b"a,b")
    (directory / f"{csv}.json").write_text(json.dumps({"filename": "mesure.csv", "content_type": "text/csv", "size": 3}), encoding="utf-8")
    assert _launch_response(client, slug, [{"image_id": csv}], title="Autre").status_code == 422


def test_upload_refuses_what_the_browser_cannot_show(client):
    slug = _owner_microproject(client)
    tiff = _upload(client, slug, "coupe.tif", "image/tiff", b"II*\x00")
    assert tiff.status_code == 422 and "collez" in tiff.json()["detail"]
    assert _upload(client, slug, "x.svg", "image/svg+xml", b"<svg onload='alert(1)'/>").status_code == 422
    assert _upload(client, slug, data=b"").status_code == 422
    assert _upload(client, slug, data=b"0" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_viewer_cannot_upload_or_launch(client):
    slug = _owner_microproject(client, "owner-img@example.com")
    image = _image(client, slug)
    join_as(client, slug, "viewer-img@example.com", owner="owner-img@example.com", role="viewer")
    assert _upload(client, slug).status_code == 403
    assert _launch_response(client, slug, [image]).status_code == 403


def test_changing_the_pictures_keeps_the_structure_version_and_the_graph_node(client):
    slug = _owner_microproject(client)
    schema = _image(client, slug, "schema")
    launched = _launch_response(client, slug, [schema]).json()
    line = launched["id"]

    # la coupe TEM arrive : on l'ajoute à côté du schéma
    tem = _image(client, slug, "coupe", "Coupe FIB-TEM")
    detail = replace_structure_images(client, slug, line, [schema, tem])
    assert detail["id"] == line
    assert [img["image_id"] for img in detail["structure_images"]] == [schema["image_id"], tem["image_id"]]
    assert detail["hypothesis"] == "Le puits fait 3 nm" and detail["intent"] == "Documenter la structure réelle"
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]
    assert structure_diff(client, slug, line, against_version=launched["version_id"])["summary"] == ["1 image ajoutée"]

    # la coupe d'abord, légende du schéma, après une étiquette : le reste suit
    before_reorder = tag(client, slug, line, ["tem"])
    detail = replace_structure_images(client, slug, line, [tem, {**schema, "caption": "Schéma PowerPoint"}])
    assert [img["image_id"] for img in detail["structure_images"]] == [tem["image_id"], schema["image_id"]]
    assert detail["structure_images"][1]["caption"] == "Schéma PowerPoint" and detail["tags"] == ["tem"]
    diff = structure_diff(client, slug, line, against_version=before_reorder["version_id"])
    assert diff["summary"] == ["Ordre des images modifié", "Image 2 : légende modifiée"]

    # l'ancienne version garde ses images
    first = get_version(client, slug, line, launched["version_id"])
    assert [img["image_id"] for img in first["structure_images"]] == [schema["image_id"]]
    assert first["structure_images"][0]["url"] == f"/api/microprojects/{slug}/attachments/{schema['image_id']}/content"

    history = versions(client, slug, line)
    assert _structural_versions(client, slug, line) == [("1.0.0", "initial")]  # même structure, autres images
    assert history[-1]["version"] == "1.0.0" and history[-1]["change_level"] == "none"
    assert [n["id"] for n in lineage(client, slug)["nodes"]] == [detail["version_id"]]

    # remettre les mêmes images : rien à enregistrer
    same = replace_structure_images(client, slug, line, [tem, {**schema, "caption": "Schéma PowerPoint"}])
    assert same["version_id"] == detail["version_id"]
    # remplacer la coupe, retirer le schéma
    better = _image(client, slug, "coupe")
    replace_structure_images(client, slug, line, [better])
    diff = structure_diff(client, slug, line, against_version=detail["version_id"])
    assert diff["summary"] == ["Image 1 remplacée", "1 image retirée"]
    assert client.put(f"{experiment_url(slug, line)}/structure-images", json={"images": []}).status_code == 422


def test_a_drawn_structure_is_not_replaced_by_pictures_through_structure_images(client):
    slug = _owner_microproject(client)
    drawn = launch(client, slug, title="Dessinée", intent="x")
    response = client.put(f"{experiment_url(slug, drawn['id'])}/structure-images", json={"images": [_image(client, slug)]})
    assert response.status_code == 422
    assert response.json()["code"] == "drawn_structure"


def test_continue_with_new_pictures_is_a_new_structure_version(client):
    slug = _owner_microproject(client)
    launched = _launch_response(client, slug, [_image(client, slug)]).json()
    pictures = [_image(client, slug, "schema"), _image(client, slug)]
    evolved = evolve_image(client, slug, launched["id"], pictures, title="Coupe TEM", intent="Puits plus épais")
    assert evolved["parents"] == [launched["version_id"]] and len(evolved["structure_images"]) == 2
    assert evolved["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]  # repris de la version précédente
    assert _structural_versions(client, slug, launched["id"]) == [("1.0.0", "initial"), ("2.0.0", "major")]
    graph = lineage(client, slug)
    assert {n["id"] for n in graph["nodes"]} == {launched["version_id"], evolved["version_id"]}
    assert graph["edges"] == [{"parent": launched["version_id"], "child": evolved["version_id"]}]


def test_switch_between_a_drawn_structure_and_pictures_both_ways(client):
    slug = _owner_microproject(client)
    drawn = launch(client, slug, intent="x")
    line = drawn["id"]

    pictured = evolve_image(client, slug, line, [_image(client, slug)], title="Essai", intent="La vraie coupe")
    assert pictured["structure_images"][0]["kind"] == "coupe" and pictured["has_editable_process"] is False
    assert_handler_404(client.get(f"{experiment_url(slug, line)}/process"), "procédé éditable")
    assert structure_diff(client, slug, line)["summary"] == [
        "Structure donnée en images (la version précédente était dessinée dans le constructeur)"
    ]

    redrawn = evolve(client, slug, line, intent="Redessinée", steps=steps(40))
    assert redrawn["structure_images"] is None and redrawn["structure_svg"] and redrawn["has_editable_process"] is True
    assert structure_diff(client, slug, line)["summary"] == [
        "Structure redessinée dans le constructeur (la version précédente était donnée en images)"
    ]

    assert _structural_versions(client, slug, line) == [("1.0.0", "initial"), ("2.0.0", "major"), ("3.0.0", "major")]
    # deux structures dessinées : pas de résumé, le diff habituel s'applique
    assert "summary" not in structure_diff(client, slug, line, against_version=drawn["version_id"])


def test_a_campaign_continued_with_pictures_follows_one_sample(client):
    slug = _owner_microproject(client)
    campaign = launch_campaign(
        client, slug, campaign_plan([10, 30]), title="Split", intent="Epaisseur", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}]
    )
    pictured = evolve_image(client, slug, campaign["id"], [_image(client, slug)], title="Split", intent="Coupe du meilleur")
    assert pictured["is_batch"] is False and pictured["structure_images"]
    assert pictured["physical_tracking"] == [{"sample_id": "W1", "location": None}]


def test_a_campaign_is_not_an_evolution(client):
    slug = _owner_microproject(client)
    launched = launch(client, slug)
    body = launch_body(kind="campaign", plan=campaign_plan([10, 30]))
    response = client.post(f"{experiment_url(slug, launched['id'])}/versions", json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "campaign_is_a_new_line"


def test_comparing_with_pictures_says_what_changed_in_words(client):
    slug = _owner_microproject(client)
    pictured = _launch_response(client, slug, [_image(client, slug)]).json()
    drawn = launch(client, slug, title="Dessinée", intent="x")
    response = structure_diff(client, slug, pictured["id"], against_experiment=drawn["id"], against_microproject=slug)
    assert response["entries"] == []
    assert response["summary"] == ["Structure donnée en images (la version précédente était dessinée dans le constructeur)"]
    assert response["target"]["experiment_id"] == drawn["id"]


def test_a_single_flat_picture_from_the_first_version_still_reads():
    # la toute première version de ce mode stockait une seule image à plat
    from spectre.plugins.structures.kinds import StructureImage, structure_images

    flat = {"image_id": "att_" + "1" * 20, "kind": "schema", "caption": "ancien"}
    assert structure_images(StructureImage.registry_key(), flat) == [flat]
    assert StructureImage.model_validate(flat).model_dump() == {"images": [flat]}
