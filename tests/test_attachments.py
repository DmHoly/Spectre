"""Pièces jointes (spectre.api.experiments's pieces-jointes routes): attaching a file to an
experience, or to one of the physical entities it tracks. Like tags/physical_tracking, uploading
or removing one records a new Follow version rather than mutating anything in place - the
uploaded bytes themselves live on disk (spectre.core.microprojects.attachments_dir), addressed by a
generated id, never the caller-supplied filename.
"""

from __future__ import annotations

import io

from support.experiments import add_evidence, get_experience, launch, track_entities, upload_attachment
from support.http import PNG_1PX, assert_handler_404
from support.microprojects import join_as, signup_with_microproject


def test_upload_attachment_records_a_new_version_and_lists_it(client):
    slug = signup_with_microproject(client, "attach@example.com")
    launched = launch(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.png", PNG_1PX, "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] != launched["id"]  # a new version, same as tags/evidence/physical_tracking
    assert body["attachment"]["filename"] == "mesure.png"
    assert body["attachment"]["content_type"] == "image/png"
    assert body["attachment"]["entity_index"] is None

    detail = get_experience(client, slug, body["id"])
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["filename"] == "mesure.png"

    atlas = client.get("/api/atlas?theme=non-classe").json()
    microproject = next(p for p in atlas["microprojects"] if p["slug"] == slug)
    assert microproject["experiences"][0]["attachments"][0]["filename"] == "mesure.png"


def test_uploaded_file_downloads_with_the_right_bytes_and_type(client):
    slug = signup_with_microproject(client, "attach-download@example.com")
    launched = launch(client, slug)
    upload = upload_attachment(client, slug, launched["id"], "wafer.png")
    attachment_id = upload["attachment"]["id"]

    download = client.get(f"/api/microprojets/{slug}/pieces-jointes/{attachment_id}")
    assert download.status_code == 200
    assert download.content == PNG_1PX
    assert download.headers["content-type"] == "image/png"
    # images are served inline (for a preview <img src>), not forced as a download
    assert "attachment" not in download.headers.get("content-disposition", "")


def test_unknown_attachment_is_404(client):
    slug = signup_with_microproject(client, "attach-unknown@example.com")
    assert_handler_404(client.get(f"/api/microprojets/{slug}/pieces-jointes/att_{'0' * 20}"))
    assert_handler_404(client.get(f"/api/microprojets/{slug}/pieces-jointes/..secret"))  # not an attachment id


def test_upload_rejects_disallowed_content_type(client):
    slug = signup_with_microproject(client, "attach-badtype@example.com")
    launched = launch(client, slug)
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("script.svg", b"<svg onload='alert(1)'></svg>", "image/svg+xml")},
    )
    assert response.status_code == 422


def test_upload_rejects_a_file_over_the_size_limit(client):
    slug = signup_with_microproject(client, "attach-toobig@example.com")
    launched = launch(client, slug)
    oversized = io.BytesIO(b"x" * (10 * 1024 * 1024 + 1))
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.csv", oversized, "text/csv")},
    )
    assert response.status_code == 422


def test_attachment_can_be_scoped_to_a_specific_physical_entity(client):
    slug = signup_with_microproject(client, "attach-entity@example.com")
    launched = launch(client, slug)
    with_entity = track_entities(client, slug, launched["id"], [{"sample_id": "W-A1"}])

    upload = client.post(
        f"/api/microprojets/{slug}/experiences/{with_entity['id']}/pieces-jointes",
        data={"entity_index": "0"},
        files={"file": ("wafer-map.png", PNG_1PX, "image/png")},
    )
    assert upload.status_code == 201
    assert upload.json()["attachment"]["entity_index"] == 0

    # entity_index out of range for this experience (only one entity, index 0) is rejected
    invalid = client.post(
        f"/api/microprojets/{slug}/experiences/{upload.json()['id']}/pieces-jointes",
        data={"entity_index": "5"},
        files={"file": ("autre.png", PNG_1PX, "image/png")},
    )
    assert invalid.status_code == 422


def test_removing_an_attachment_records_a_new_version_without_it(client):
    slug = signup_with_microproject(client, "attach-remove@example.com")
    launched = launch(client, slug)
    upload = upload_attachment(client, slug, launched["id"], "mesure.txt", b"42", "text/plain")
    attachment_id = upload["attachment"]["id"]

    removed = client.delete(f"/api/microprojets/{slug}/experiences/{upload['id']}/pieces-jointes/{attachment_id}")
    assert removed.status_code == 200
    new_id = removed.json()["id"]
    assert new_id != upload["id"]

    assert get_experience(client, slug, new_id)["attachments"] == []

    # the file itself is left on disk (an older, still-immutable version still lists it) and
    # remains downloadable
    download = client.get(f"/api/microprojets/{slug}/pieces-jointes/{attachment_id}")
    assert download.status_code == 200

    # but there is nothing left to remove from the new version
    again = client.delete(f"/api/microprojets/{slug}/experiences/{new_id}/pieces-jointes/{attachment_id}")
    assert_handler_404(again, "pièce jointe introuvable")


def test_attachment_can_be_scoped_to_a_preuve_and_then_annotated(client):
    slug = signup_with_microproject(client, "attach-evidence@example.com")
    launched = launch(client, slug)
    with_evidence = add_evidence(client, slug, launched["id"], "SEM du bord", source="—", kind="image")
    evidence_id = with_evidence["evidence_id"]

    upload = client.post(
        f"/api/microprojets/{slug}/experiences/{with_evidence['id']}/pieces-jointes",
        data={"evidence_id": evidence_id},
        files={"file": ("sem.png", PNG_1PX, "image/png")},
    )
    assert upload.status_code == 201
    assert upload.json()["attachment"]["evidence_id"] == evidence_id
    attachment_id = upload.json()["attachment"]["id"]
    version_with_image = upload.json()["id"]

    # evidence_id that doesn't exist on this experience is rejected
    invalid = client.post(
        f"/api/microprojets/{slug}/experiences/{version_with_image}/pieces-jointes",
        data={"evidence_id": "does-not-exist"},
        files={"file": ("autre.png", PNG_1PX, "image/png")},
    )
    assert invalid.status_code == 422

    annotated = client.post(
        f"/api/microprojets/{slug}/experiences/{version_with_image}/preuves/{evidence_id}/annotations",
        json={
            "annotations": [
                {"attachment_id": attachment_id, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut ici"},
                {"attachment_id": attachment_id, "type": "arrow", "x": 5.0, "y": 5.0, "x2": 15.0, "y2": 15.0, "label": None},
            ]
        },
    )
    assert annotated.status_code == 200

    detail = get_experience(client, slug, annotated.json()["id"])
    evidence = next(e for e in detail["evidence"] if e["id"] == evidence_id)
    assert evidence["kind"] == "image"  # the preuve's own fields survived the annotation version too
    assert len(evidence["image_annotations"]) == 2
    assert evidence["image_annotations"][0]["label"] == "défaut ici"
    # the attachment itself carried forward unaffected
    assert detail["attachments"][0]["id"] == attachment_id


def test_annotations_reject_an_attachment_that_does_not_belong_to_the_preuve(client):
    slug = signup_with_microproject(client, "attach-annot-mismatch@example.com")
    launched = launch(client, slug)
    with_evidence = add_evidence(client, slug, launched["id"], "SEM", source="—", kind="image")
    evidence_id = with_evidence["evidence_id"]

    # an attachment not scoped to this evidence at all (whole-study attachment)
    upload = upload_attachment(client, slug, with_evidence["id"], "autre.png")

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{upload['id']}/preuves/{evidence_id}/annotations",
        json={"annotations": [{"attachment_id": upload["attachment"]["id"], "type": "box", "x": 1.0, "y": 1.0}]},
    )
    assert response.status_code == 422


def test_annotations_on_a_nonexistent_evidence_id_is_404(client):
    slug = signup_with_microproject(client, "attach-annot-404@example.com")
    launched = launch(client, slug)
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/preuves/does-not-exist/annotations",
        json={"annotations": []},
    )
    assert_handler_404(response, "preuve introuvable")


def test_viewer_cannot_upload_an_attachment(client):
    owner_slug = signup_with_microproject(client, "attach-owner@example.com")
    launched = launch(client, owner_slug)

    join_as(client, owner_slug, "attach-viewer@example.com", owner="attach-owner@example.com", role="viewer")
    response = client.post(
        f"/api/microprojets/{owner_slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.txt", b"42", "text/plain")},
    )
    assert response.status_code == 403
