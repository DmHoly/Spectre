"""Les images d'une preuve : téléversées d'abord (POST .../attachments, ``purpose=evidence``, plugin
attachments), puis rattachées à la preuve qui les montre (plugin evidence) - c'est le seul chemin du
front, les anciennes routes « pièces jointes » d'une expérience ont disparu. La preuve et ses images
entrent dans une seule nouvelle version de la piste ; les octets restent servis par attachments.
Le téléversement lui-même est testé dans test_uploads.py.
"""

from __future__ import annotations

from support.experiments import add_evidence, experiment_url, get_experiment, launch, upload_image
from support.http import PNG_1PX, assert_handler_404
from support.microprojects import join_as, signup_with_microproject


def _annotations_url(slug, ref, evidence_id):
    return f"/api/microprojets/{slug}/experiences/{ref}/preuves/{evidence_id}/annotations"


def test_the_old_attachment_routes_of_an_experiment_are_gone(client):
    slug = signup_with_microproject(client, "attach-gone@example.com")
    launched = launch(client, slug)
    files = {"file": ("mesure.png", PNG_1PX, "image/png")}
    for url in (f"/api/microprojets/{slug}/experiences/{launched['id']}/pieces-jointes", f"{experiment_url(slug, launched['id'])}/attachments"):
        assert client.post(url, files=files).status_code == 404


def test_pasted_images_become_the_evidence_attachments_in_one_version(client):
    slug = signup_with_microproject(client, "attach@example.com")
    launched = launch(client, slug)
    image_id = upload_image(client, slug, "sem.png")

    added = add_evidence(client, slug, launched["id"], "SEM du bord", images=[{"image_id": image_id, "caption": " bord gauche "}])
    detail = get_experiment(client, slug, launched["id"])
    assert detail["version_id"] == added["version_id"]
    [attachment] = detail["attachments"]
    assert (attachment["id"], attachment["filename"], attachment["evidence_id"]) == (image_id, "sem.png", added["evidence_id"])
    assert attachment["caption"] == "bord gauche"
    assert next(e for e in detail["evidence"] if e["id"] == added["evidence_id"])["kind"] == "image"

    download = client.get(f"/api/microprojects/{slug}/attachments/{image_id}/content")
    assert download.status_code == 200 and download.content == PNG_1PX
    assert download.headers["content-type"] == "image/png"

    atlas = client.get("/api/atlas?theme=non-classe").json()
    microproject = next(p for p in atlas["microprojects"] if p["slug"] == slug)
    assert microproject["experiences"][0]["attachments"][0]["filename"] == "sem.png"


def test_an_evidence_image_must_be_an_uploaded_image_of_this_microproject(client):
    slug = signup_with_microproject(client, "attach-unknown@example.com")
    launched = launch(client, slug)
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y", "images": [{"image_id": f"att_{'0' * 20}"}]},
    )
    assert response.status_code == 422
    assert get_experiment(client, slug, launched["id"])["version_id"] == launched["version_id"]  # rien d'écrit


def test_unknown_attachment_is_404(client):
    slug = signup_with_microproject(client, "attach-404@example.com")
    for suffix in ("", "/content"):
        assert_handler_404(client.get(f"/api/microprojects/{slug}/attachments/att_{'0' * 20}{suffix}"))
        assert_handler_404(client.get(f"/api/microprojects/{slug}/attachments/..secret{suffix}"))  # not an attachment id


def test_an_evidence_image_can_be_annotated(client):
    slug = signup_with_microproject(client, "attach-evidence@example.com")
    launched = launch(client, slug)
    image_id = upload_image(client, slug, "sem.png")
    added = add_evidence(client, slug, launched["id"], "SEM du bord", source="—", images=[{"image_id": image_id}])
    evidence_id = added["evidence_id"]

    annotated = client.post(
        _annotations_url(slug, launched["id"], evidence_id),
        json={
            "annotations": [
                {"attachment_id": image_id, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut ici"},
                {"attachment_id": image_id, "type": "arrow", "x": 5.0, "y": 5.0, "x2": 15.0, "y2": 15.0, "label": None},
            ]
        },
    )
    assert annotated.status_code == 200
    assert annotated.json()["id"] == launched["id"]

    detail = get_experiment(client, slug, launched["id"])
    evidence = next(e for e in detail["evidence"] if e["id"] == evidence_id)
    assert evidence["kind"] == "image"  # the preuve's own fields survived the annotation version too
    assert len(evidence["image_annotations"]) == 2
    assert evidence["image_annotations"][0]["label"] == "défaut ici"
    assert detail["attachments"][0]["id"] == image_id  # the image itself carried forward unaffected


def test_annotations_reject_an_image_that_does_not_belong_to_the_preuve(client):
    slug = signup_with_microproject(client, "attach-annot-mismatch@example.com")
    launched = launch(client, slug)
    first = add_evidence(client, slug, launched["id"], "SEM", images=[{"image_id": upload_image(client, slug)}])
    other_image = upload_image(client, slug, "autre.png")
    add_evidence(client, slug, launched["id"], "Autre", images=[{"image_id": other_image}])

    response = client.post(
        _annotations_url(slug, launched["id"], first["evidence_id"]),
        json={"annotations": [{"attachment_id": other_image, "type": "box", "x": 1.0, "y": 1.0}]},
    )
    assert response.status_code == 422


def test_annotations_on_a_nonexistent_evidence_id_is_404(client):
    slug = signup_with_microproject(client, "attach-annot-404@example.com")
    launched = launch(client, slug)
    response = client.post(_annotations_url(slug, launched["id"], "does-not-exist"), json={"annotations": []})
    assert_handler_404(response, "preuve introuvable")


def test_viewer_cannot_add_an_evidence_image(client):
    owner_slug = signup_with_microproject(client, "attach-owner@example.com")
    launched = launch(client, owner_slug)
    image_id = upload_image(client, owner_slug)

    join_as(client, owner_slug, "attach-viewer@example.com", owner="attach-owner@example.com", role="viewer")
    response = client.post(
        f"/api/microprojets/{owner_slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y", "images": [{"image_id": image_id}]},
    )
    assert response.status_code == 403
