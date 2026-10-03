"""Les images d'une preuve : téléversées d'abord (POST .../attachments, ``purpose=evidence``, plugin
attachments), puis rattachées à la preuve qui les montre (plugin evidence, testé dans
``tests/plugins/evidence``) - c'est le seul chemin du front, les anciennes routes « pièces jointes »
d'une expérience ont disparu. Les octets restent servis par attachments. Le téléversement lui-même
est testé dans test_uploads.py.
"""

from __future__ import annotations

from support.evidence import add_evidence, upload_image
from support.experiments import experiment_url, launch
from support.http import PNG_1PX, assert_handler_404
from support.microprojects import signup_with_microproject


def test_the_old_attachment_routes_of_an_experiment_are_gone(client):
    slug = signup_with_microproject(client, "attach-gone@example.com")
    launched = launch(client, slug)
    files = {"file": ("mesure.png", PNG_1PX, "image/png")}
    for url in (f"/api/microprojets/{slug}/experiences/{launched['id']}/pieces-jointes", f"{experiment_url(slug, launched['id'])}/attachments"):
        assert client.post(url, files=files).status_code == 404


def test_an_evidence_image_is_served_by_attachments_and_shown_by_the_atlas(client):
    slug = signup_with_microproject(client, "attach@example.com")
    launched = launch(client, slug)
    image_id = upload_image(client, slug, "sem.png")

    [image] = add_evidence(client, slug, launched["id"], "SEM du bord", images=[{"image_id": image_id}])["images"]
    assert image["url"] == f"/api/microprojects/{slug}/attachments/{image_id}/content"
    download = client.get(image["url"])
    assert download.status_code == 200 and download.content == PNG_1PX
    assert download.headers["content-type"] == "image/png"

    atlas = client.get("/api/atlas?theme=non-classe").json()
    microproject = next(p for p in atlas["microprojects"] if p["slug"] == slug)
    assert microproject["experiences"][0]["attachments"][0]["filename"] == "sem.png"


def test_unknown_attachment_is_404(client):
    slug = signup_with_microproject(client, "attach-404@example.com")
    for suffix in ("", "/content"):
        assert_handler_404(client.get(f"/api/microprojects/{slug}/attachments/att_{'0' * 20}{suffix}"))
        assert_handler_404(client.get(f"/api/microprojects/{slug}/attachments/..secret{suffix}"))  # not an attachment id
