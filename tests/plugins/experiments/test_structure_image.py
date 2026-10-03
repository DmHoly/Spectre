"""Structure en image (spectre.plugins.structures.kinds.StructureImage): an experience launched without the
builder, whose structure is given as pictures - a PowerPoint schematic, TEM cross-sections... one or
several, in reading order - that can be changed later (a lightweight evolution, same structure
version) or continued with new ones (a real evolution, new version), including to and from a
structure drawn in the builder.
"""

from __future__ import annotations

from support.attachments import post_attachment
from support.experiments import evolve, get_experience, launch, launch_campaign, lineage, tag, timeline
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
    return client.post(
        f"/api/microprojets/{slug}/experiences/image",
        json={
            "images": images,
            "title": title,
            "intent": "Documenter la structure réelle",
            "hypothesis": "Le puits fait 3 nm",
            "entities": [{"sample_id": ""}, {"sample_id": "W7", "location": "boîte 3"}],
            **extra,
        },
    )


def test_launch_an_experience_with_several_pictures(client):
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
    detail = get_experience(client, slug, launched.json()["id"])
    assert detail["structure_images"] == [
        {"image_id": image["id"], "kind": "schema", "caption": None},
        {"image_id": overview["image_id"], "kind": "coupe", "caption": "Coupe FIB du wafer W7"},
    ]
    assert detail["structure_svg"] is None and detail["is_batch"] is False and detail["has_editable_process"] is False
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]
    assert detail["ref_names"]  # la toute première expérience du µprojet devient sa première ref
    # pas de procédé éditable : la fiche n'a rien à rouvrir dans le constructeur
    assert_handler_404(client.get(f"/api/microprojets/{slug}/experiences/{launched.json()['id']}/process"), "procédé éditable")
    history = timeline(client, slug, launched.json()["id"])
    assert [(v["version"], v["change_level"]) for v in history["versions"]] == [("1.0.0", "initial")]


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

    # une pièce jointe non image (un CSV...) ne peut pas servir d'image de structure
    csv = client.post(
        f"/api/microprojets/{slug}/experiences/{_launch_response(client, slug, [good]).json()['id']}/pieces-jointes",
        files={"file": ("mesure.csv", b"a,b", "text/csv")},
    ).json()["attachment"]["id"]
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

    # la coupe TEM arrive : on l'ajoute à côté du schéma
    tem = _image(client, slug, "coupe", "Coupe FIB-TEM")
    added = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/dessin", json={"images": [schema, tem]})
    assert added.status_code == 201
    detail = get_experience(client, slug, added.json()["id"])
    assert [img["image_id"] for img in detail["structure_images"]] == [schema["image_id"], tem["image_id"]]
    assert detail["hypothesis"] == "Le puits fait 3 nm" and detail["intent"] == "Documenter la structure réelle"
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]
    diff = client.get(f"/api/microprojets/{slug}/experiences/{added.json()['id']}/diff").json()
    assert diff["summary"] == ["1 image ajoutée"]

    # la coupe d'abord, légende du schéma, après une étiquette : le reste suit
    tagged = tag(client, slug, added.json()["id"], ["tem"])
    reordered = client.post(
        f"/api/microprojets/{slug}/experiences/{tagged['id']}/dessin",
        json={"images": [tem, {**schema, "caption": "Schéma PowerPoint"}]},
    )
    new_id = reordered.json()["id"]
    detail = get_experience(client, slug, new_id)
    assert [img["image_id"] for img in detail["structure_images"]] == [tem["image_id"], schema["image_id"]]
    assert detail["structure_images"][1]["caption"] == "Schéma PowerPoint" and detail["tags"] == ["tem"]
    diff = client.get(f"/api/microprojets/{slug}/experiences/{new_id}/diff").json()
    assert diff["summary"] == ["Ordre des images modifié", "Image 2 : légende modifiée"]

    # l'ancienne version garde ses images
    assert [img["image_id"] for img in get_experience(client, slug, launched["id"])["structure_images"]] == [schema["image_id"]]

    history = timeline(client, slug, new_id)
    assert [v["version"] for v in history["versions"]] == ["1.0.0"]  # même structure, autres images
    assert history["items"][-1]["version"] == "1.0.0" and history["items"][-1]["change_level"] == "none"
    graph = lineage(client, slug)
    assert [n["id"] for n in graph["nodes"]] == [new_id]

    # remettre les mêmes images : rien à enregistrer
    same = client.post(
        f"/api/microprojets/{slug}/experiences/{new_id}/dessin",
        json={"images": [tem, {**schema, "caption": "Schéma PowerPoint"}]},
    )
    assert same.json()["id"] == new_id
    # remplacer la coupe, retirer le schéma
    better = _image(client, slug, "coupe")
    replaced = client.post(f"/api/microprojets/{slug}/experiences/{new_id}/dessin", json={"images": [better]}).json()
    diff = client.get(f"/api/microprojets/{slug}/experiences/{replaced['id']}/diff").json()
    assert diff["summary"] == ["Image 1 remplacée", "1 image retirée"]
    assert client.post(f"/api/microprojets/{slug}/experiences/{replaced['id']}/dessin", json={"images": []}).status_code == 422


def test_a_drawn_structure_is_not_replaced_by_pictures_through_dessin(client):
    slug = _owner_microproject(client)
    drawn = launch(client, slug, title="Dessinée", intent="x")
    response = client.post(f"/api/microprojets/{slug}/experiences/{drawn['id']}/dessin", json={"images": [_image(client, slug)]})
    assert response.status_code == 422


def test_continue_with_new_pictures_is_a_new_structure_version(client):
    slug = _owner_microproject(client)
    launched = _launch_response(client, slug, [_image(client, slug)]).json()
    evolved = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer-image",
        json={"images": [_image(client, slug, "schema"), _image(client, slug)], "title": "Coupe TEM", "intent": "Puits plus épais"},
    )
    assert evolved.status_code == 201
    detail = get_experience(client, slug, evolved.json()["id"])
    assert detail["parents"] == [launched["id"]] and len(detail["structure_images"]) == 2
    assert detail["physical_tracking"] == [{"sample_id": "W7", "location": "boîte 3"}]  # repris de la version précédente
    history = timeline(client, slug, evolved.json()["id"])
    assert [(v["version"], v["change_level"]) for v in history["versions"]] == [("1.0.0", "initial"), ("2.0.0", "major")]
    graph = lineage(client, slug)
    assert {n["id"] for n in graph["nodes"]} == {launched["id"], evolved.json()["id"]}
    assert graph["edges"] == [{"parent": launched["id"], "child": evolved.json()["id"]}]


def test_switch_between_a_drawn_structure_and_pictures_both_ways(client):
    slug = _owner_microproject(client)
    drawn = launch(client, slug, intent="x")

    pictured = client.post(
        f"/api/microprojets/{slug}/experiences/{drawn['id']}/evoluer-image",
        json={"images": [_image(client, slug)], "title": "Essai", "intent": "La vraie coupe"},
    ).json()
    detail = get_experience(client, slug, pictured["id"])
    assert detail["structure_images"][0]["kind"] == "coupe" and detail["has_editable_process"] is False
    assert_handler_404(client.get(f"/api/microprojets/{slug}/experiences/{pictured['id']}/process"), "procédé éditable")
    diff = client.get(f"/api/microprojets/{slug}/experiences/{pictured['id']}/diff").json()
    assert diff["summary"] == ["Structure donnée en images (la version précédente était dessinée dans le constructeur)"]

    redrawn = evolve(client, slug, pictured["id"], intent="Redessinée", steps=steps(40), objectives=[])
    detail = get_experience(client, slug, redrawn["id"])
    assert detail["structure_images"] is None and detail["structure_svg"] and detail["has_editable_process"] is True
    diff = client.get(f"/api/microprojets/{slug}/experiences/{redrawn['id']}/diff").json()
    assert diff["summary"] == ["Structure redessinée dans le constructeur (la version précédente était donnée en images)"]

    history = timeline(client, slug, redrawn["id"])
    assert [(v["version"], v["change_level"]) for v in history["versions"]] == [
        ("1.0.0", "initial"),
        ("2.0.0", "major"),
        ("3.0.0", "major"),
    ]
    # deux structures dessinées : pas de résumé, le diff habituel s'applique
    assert "summary" not in client.get(f"/api/microprojets/{slug}/experiences/{drawn['id']}/diff").json()


def test_a_campaign_continued_with_pictures_follows_one_sample(client):
    slug = _owner_microproject(client)
    campaign = launch_campaign(
        client, slug, campaign_plan([10, 30]), title="Split", intent="Epaisseur", entities=[{"sample_id": "W1"}, {"sample_id": "W2"}]
    )
    pictured = client.post(
        f"/api/microprojets/{slug}/experiences/{campaign['id']}/evoluer-image",
        json={"images": [_image(client, slug)], "title": "Split", "intent": "Coupe du meilleur"},
    ).json()
    detail = get_experience(client, slug, pictured["id"])
    assert detail["is_batch"] is False and detail["structure_images"]
    assert detail["physical_tracking"] == [{"sample_id": "W1", "location": None}]


def test_comparing_with_pictures_says_it_cannot(client):
    slug = _owner_microproject(client)
    pictured = _launch_response(client, slug, [_image(client, slug)]).json()
    drawn = launch(client, slug, title="Dessinée", intent="x")
    response = client.get(
        f"/api/microprojets/{slug}/experiences/{pictured['id']}/diff-externe?autre_projet={slug}&autre_experience={drawn['id']}"
    ).json()
    assert response["entries"] == [] and "images" in response["note"]


def test_a_single_flat_picture_from_the_first_version_still_reads():
    # la toute première version de ce mode stockait une seule image à plat
    from spectre.plugins.structures.kinds import StructureImage, structure_images

    flat = {"image_id": "att_" + "1" * 20, "kind": "schema", "caption": "ancien"}
    assert structure_images(StructureImage.registry_key(), flat) == [flat]
    assert StructureImage.model_validate(flat).model_dump() == {"images": [flat]}
