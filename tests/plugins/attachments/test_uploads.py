"""Fichiers téléversés d'un µprojet (spectre.plugins.attachments) : POST .../attachments, ses
métadonnées et ses octets ; types et tailles fixés par l'usage (purpose), lecture bornée, et les
sidecars écrits avant ``purpose`` toujours lisibles."""

from __future__ import annotations

import io
import json

import pytest

from spectre.kernel.errors import InvalidInput
from spectre.plugins.attachments import store
from support.attachments import attachments_url, post_attachment, upload_file
from support.http import PNG_1PX, assert_handler_404, assert_ok
from support.microprojects import join_as, signup_with_microproject


def test_upload_creates_the_attachment_with_its_location(client):
    slug = signup_with_microproject(client, "upload@example.com", name="Ada")
    response = post_attachment(client, slug, "structure", "coupe.png")
    assert response.status_code == 201
    created = response.json()
    assert created["id"].startswith("att_")
    assert response.headers["location"] == f"{attachments_url(slug)}/{created['id']}"
    assert created["url"] == f"{attachments_url(slug)}/{created['id']}/content"
    assert (created["filename"], created["content_type"], created["size"], created["purpose"]) == ("coupe.png", "image/png", len(PNG_1PX), "structure")
    assert created["uploaded_by"] == "Ada" and created["uploaded_at"]

    assert assert_ok(client.get(response.headers["location"])) == created
    content = client.get(created["url"])
    assert content.status_code == 200 and content.content == PNG_1PX
    assert content.headers["content-type"] == "image/png"
    assert content.headers["x-content-type-options"] == "nosniff"
    assert "attachment" not in content.headers.get("content-disposition", "")  # une image s'affiche


def test_an_evidence_image_has_its_purpose(client):
    slug = signup_with_microproject(client, "upload-evidence@example.com")
    assert upload_file(client, slug, "evidence")["purpose"] == "evidence"


def test_upload_refuses_an_unknown_or_missing_purpose(client):
    slug = signup_with_microproject(client, "upload-purpose@example.com")
    unknown = post_attachment(client, slug, "rapport")
    assert unknown.status_code == 422 and "structure" in unknown.json()["detail"]
    missing = client.post(attachments_url(slug), files={"file": ("schema.png", PNG_1PX, "image/png")})
    assert missing.status_code == 422


@pytest.mark.parametrize("purpose", ["structure", "evidence"])
def test_upload_refuses_what_the_browser_cannot_show(client, purpose):
    slug = signup_with_microproject(client, "upload-types@example.com")
    tiff = post_attachment(client, slug, purpose, "coupe.tif", b"II*\x00", "image/tiff")
    assert tiff.status_code == 422 and "collez" in tiff.json()["detail"]
    assert post_attachment(client, slug, purpose, "x.svg", b"<svg onload='alert(1)'/>", "image/svg+xml").status_code == 422
    assert post_attachment(client, slug, purpose, "mesure.csv", b"a,b", "text/csv").status_code == 422
    assert post_attachment(client, slug, purpose, content=b"").status_code == 422


def test_a_file_over_the_limit_is_413_and_leaves_nothing_on_disk(client):
    slug = signup_with_microproject(client, "upload-big@example.com")
    response = post_attachment(client, slug, content=io.BytesIO(b"0" * (store.IMAGE_MAX_BYTES + 1)))
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert list(store.attachments_dir(slug).iterdir()) == []
    # exactement la limite : accepté
    assert upload_file(client, slug, content=io.BytesIO(b"0" * store.IMAGE_MAX_BYTES))["size"] == store.IMAGE_MAX_BYTES


class _Endless(io.RawIOBase):
    """Un flux sans fin, qui compte ce qu'on lui a lu."""

    def __init__(self) -> None:
        self.served = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        assert size > 0, "lecture non bornée"
        self.served += size
        return b"0" * size


def test_the_upload_is_read_chunk_by_chunk_and_stops_at_the_limit(client):
    slug = signup_with_microproject(client, "upload-stream@example.com")
    stream = _Endless()
    with pytest.raises(store.TooLarge):
        store.save(slug, stream, filename="x.png", content_type="image/png", purpose="structure", uploaded_by="T")
    assert stream.served <= store.IMAGE_MAX_BYTES + store.CHUNK_BYTES


def test_a_viewer_reads_but_does_not_upload_and_a_stranger_reads_nothing(client):
    slug = signup_with_microproject(client, "upload-owner@example.com")
    created = upload_file(client, slug)

    join_as(client, slug, "upload-viewer@example.com", owner="upload-owner@example.com", role="viewer")
    assert post_attachment(client, slug).status_code == 403
    assert client.get(created["url"]).status_code == 200

    signup_with_microproject(client, "upload-stranger@example.com")
    assert client.get(created["url"]).status_code == 403
    assert client.get(f"{attachments_url(slug)}/{created['id']}").status_code == 403


def _legacy(slug: str, sidecar: dict, contents: bytes = PNG_1PX) -> str:
    attachment_id = store.new_attachment_id()
    directory = store.attachments_dir(slug)
    (directory / attachment_id).write_bytes(contents)
    (directory / f"{attachment_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return attachment_id


def test_sidecars_written_before_purpose_stay_readable(client):
    slug = signup_with_microproject(client, "upload-legacy@example.com")
    # une image collée dans une preuve (POST /images), avec son ``role``
    evidence = _legacy(
        slug,
        {"filename": "tem.png", "content_type": "image/png", "size": len(PNG_1PX), "role": "preuve", "uploaded_by": "Ada", "uploaded_at": "2025-01-02T03:04:05+00:00"},
    )
    assert assert_ok(client.get(f"{attachments_url(slug)}/{evidence}")) == {
        "id": evidence,
        "url": f"{attachments_url(slug)}/{evidence}/content",
        "filename": "tem.png",
        "content_type": "image/png",
        "size": len(PNG_1PX),
        "purpose": "evidence",
        "uploaded_by": "Ada",
        "uploaded_at": "2025-01-02T03:04:05+00:00",
    }
    structure = _legacy(slug, {"filename": "s.png", "content_type": "image/png", "size": 1, "role": "structure"})
    assert assert_ok(client.get(f"{attachments_url(slug)}/{structure}"))["purpose"] == "structure"

    # une pièce jointe d'expérience : ni usage ni auteur ; un fichier non image se télécharge
    csv = _legacy(slug, {"filename": "mésure.csv", "content_type": "text/csv", "size": 3}, b"a,b")
    metadata = assert_ok(client.get(f"{attachments_url(slug)}/{csv}"))
    assert (metadata["purpose"], metadata["uploaded_by"], metadata["uploaded_at"]) == (None, None, None)
    content = client.get(metadata["url"])
    assert content.content == b"a,b"
    assert content.headers["content-disposition"] == 'attachment; filename="msure.csv"'


def test_a_structure_image_must_be_an_uploaded_image(client):
    slug = signup_with_microproject(client, "upload-check@example.com")
    image = upload_file(client, slug)
    assert store.uploaded_image(slug, image["id"])["filename"] == "schema.png"
    csv = _legacy(slug, {"filename": "m.csv", "content_type": "text/csv", "size": 3}, b"a,b")
    for bad in (csv, f"att_{'0' * 20}", "../secret"):
        with pytest.raises(InvalidInput):
            store.uploaded_image(slug, bad)


def test_unknown_attachment_is_404(client):
    slug = signup_with_microproject(client, "upload-404@example.com")
    assert_handler_404(client.get(f"{attachments_url(slug)}/att_{'0' * 20}"), "introuvable")
    assert_handler_404(client.get(f"{attachments_url(slug)}/att_{'0' * 20}/content"), "introuvable")
