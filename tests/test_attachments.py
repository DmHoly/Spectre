"""Pièces jointes (spectre.api.experiments's pieces-jointes routes): attaching a file to an
experience, or to one of the physical entities it tracks. Like tags/physical_tracking, uploading
or removing one records a new Follow version rather than mutating anything in place - the
uploaded bytes themselves live on disk (spectre.core.projects.attachments_dir), addressed by a
generated id, never the caller-supplied filename.
"""

from __future__ import annotations

import io


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def _launch(client, slug, title="Etude"):
    return client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": title,
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()


def _png_bytes():
    # A minimal valid 1x1 PNG - real magic bytes, not that this route inspects them (it trusts
    # the browser-supplied content type, same as every other upload endpoint of this size).
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
        "de000000097048597300000b1300000b1301009a9c1800000010494441545805"
        "0763f8ffff3f0005fe02fea739667e0000000049454e44ae426082"
    )


def test_upload_attachment_records_a_new_version_and_lists_it(client):
    slug = _register_and_project(client, "attach@example.com")
    launched = _launch(client, slug)

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] != launched["id"]  # a new version, same as tags/evidence/physical_tracking
    assert body["attachment"]["filename"] == "mesure.png"
    assert body["attachment"]["content_type"] == "image/png"
    assert body["attachment"]["entity_index"] is None

    detail = client.get(f"/api/projects/{slug}/experiences/{body['id']}").json()
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["filename"] == "mesure.png"

    atlas = client.get("/api/atlas").json()
    project = next(p for p in atlas["projects"] if p["slug"] == slug)
    assert project["experiences"][0]["attachments"][0]["filename"] == "mesure.png"


def test_uploaded_file_downloads_with_the_right_bytes_and_type(client):
    slug = _register_and_project(client, "attach-download@example.com")
    launched = _launch(client, slug)
    png = _png_bytes()
    upload = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("wafer.png", png, "image/png")},
    ).json()
    attachment_id = upload["attachment"]["id"]

    download = client.get(f"/api/projects/{slug}/pieces-jointes/{attachment_id}")
    assert download.status_code == 200
    assert download.content == png
    assert download.headers["content-type"] == "image/png"
    # images are served inline (for a preview <img src>), not forced as a download
    assert "attachment" not in download.headers.get("content-disposition", "")


def test_upload_rejects_disallowed_content_type(client):
    slug = _register_and_project(client, "attach-badtype@example.com")
    launched = _launch(client, slug)
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("script.svg", b"<svg onload='alert(1)'></svg>", "image/svg+xml")},
    )
    assert response.status_code == 422


def test_upload_rejects_a_file_over_the_size_limit(client):
    slug = _register_and_project(client, "attach-toobig@example.com")
    launched = _launch(client, slug)
    oversized = io.BytesIO(b"x" * (10 * 1024 * 1024 + 1))
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.csv", oversized, "text/csv")},
    )
    assert response.status_code == 422


def test_attachment_can_be_scoped_to_a_specific_physical_entity(client):
    slug = _register_and_project(client, "attach-entity@example.com")
    launched = _launch(client, slug)
    with_entity = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W-A1"}]},
    ).json()

    upload = client.post(
        f"/api/projects/{slug}/experiences/{with_entity['id']}/pieces-jointes",
        data={"entity_index": "0"},
        files={"file": ("wafer-map.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201
    assert upload.json()["attachment"]["entity_index"] == 0

    # entity_index out of range for this experience (only one entity, index 0) is rejected
    invalid = client.post(
        f"/api/projects/{slug}/experiences/{upload.json()['id']}/pieces-jointes",
        data={"entity_index": "5"},
        files={"file": ("autre.png", _png_bytes(), "image/png")},
    )
    assert invalid.status_code == 422


def test_removing_an_attachment_records_a_new_version_without_it(client):
    slug = _register_and_project(client, "attach-remove@example.com")
    launched = _launch(client, slug)
    upload = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.txt", b"42", "text/plain")},
    ).json()

    removed = client.delete(f"/api/projects/{slug}/experiences/{upload['id']}/pieces-jointes/{upload['attachment']['id']}")
    assert removed.status_code == 200
    new_id = removed.json()["id"]
    assert new_id != upload["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{new_id}").json()
    assert detail["attachments"] == []

    # the file itself is left on disk (an older, still-immutable version still lists it) and
    # remains downloadable
    download = client.get(f"/api/projects/{slug}/pieces-jointes/{upload['attachment']['id']}")
    assert download.status_code == 200


def test_attachment_can_be_scoped_to_a_preuve_and_then_annotated(client):
    slug = _register_and_project(client, "attach-evidence@example.com")
    launched = _launch(client, slug)
    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "SEM du bord", "source": "—", "kind": "image"},
    ).json()
    evidence_id = with_evidence["evidence_id"]

    upload = client.post(
        f"/api/projects/{slug}/experiences/{with_evidence['id']}/pieces-jointes",
        data={"evidence_id": evidence_id},
        files={"file": ("sem.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201
    assert upload.json()["attachment"]["evidence_id"] == evidence_id
    attachment_id = upload.json()["attachment"]["id"]
    version_with_image = upload.json()["id"]

    # evidence_id that doesn't exist on this experience is rejected
    invalid = client.post(
        f"/api/projects/{slug}/experiences/{version_with_image}/pieces-jointes",
        data={"evidence_id": "does-not-exist"},
        files={"file": ("autre.png", _png_bytes(), "image/png")},
    )
    assert invalid.status_code == 422

    annotated = client.post(
        f"/api/projects/{slug}/experiences/{version_with_image}/preuves/{evidence_id}/annotations",
        json={
            "annotations": [
                {"attachment_id": attachment_id, "type": "box", "x": 10.0, "y": 20.0, "x2": 30.0, "y2": 40.0, "label": "défaut ici"},
                {"attachment_id": attachment_id, "type": "arrow", "x": 5.0, "y": 5.0, "x2": 15.0, "y2": 15.0, "label": None},
            ]
        },
    )
    assert annotated.status_code == 200

    detail = client.get(f"/api/projects/{slug}/experiences/{annotated.json()['id']}").json()
    evidence = next(e for e in detail["evidence"] if e["id"] == evidence_id)
    assert len(evidence["image_annotations"]) == 2
    assert evidence["image_annotations"][0]["label"] == "défaut ici"
    # the attachment itself carried forward unaffected
    assert detail["attachments"][0]["id"] == attachment_id


def test_annotations_reject_an_attachment_that_does_not_belong_to_the_preuve(client):
    slug = _register_and_project(client, "attach-annot-mismatch@example.com")
    launched = _launch(client, slug)
    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "SEM", "source": "—", "kind": "image"},
    ).json()
    evidence_id = with_evidence["evidence_id"]

    # an attachment not scoped to this evidence at all (whole-study attachment)
    upload = client.post(
        f"/api/projects/{slug}/experiences/{with_evidence['id']}/pieces-jointes",
        files={"file": ("autre.png", _png_bytes(), "image/png")},
    ).json()

    response = client.post(
        f"/api/projects/{slug}/experiences/{upload['id']}/preuves/{evidence_id}/annotations",
        json={"annotations": [{"attachment_id": upload["attachment"]["id"], "type": "box", "x": 1.0, "y": 1.0}]},
    )
    assert response.status_code == 422


def test_annotations_on_a_nonexistent_evidence_id_is_404(client):
    slug = _register_and_project(client, "attach-annot-404@example.com")
    launched = _launch(client, slug)
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves/does-not-exist/annotations",
        json={"annotations": []},
    )
    assert response.status_code == 404


def test_viewer_cannot_upload_an_attachment(client):
    owner_slug = _register_and_project(client, "attach-owner@example.com")
    launched = _launch(client, owner_slug)

    # the viewer's account must already exist for /members to add them directly (otherwise it
    # creates a pending invitation instead) - see test_permissions.py for the same ordering.
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "attach-viewer@example.com", "password": "supersecret", "name": "V"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "attach-owner@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{owner_slug}/members", json={"email": "attach-viewer@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "attach-viewer@example.com", "password": "supersecret"})
    response = client.post(
        f"/api/projects/{owner_slug}/experiences/{launched['id']}/pieces-jointes",
        files={"file": ("mesure.txt", b"42", "text/plain")},
    )
    assert response.status_code == 403
