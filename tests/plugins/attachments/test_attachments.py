"""Les fichiers d'une entrée du cahier : téléversés d'abord (POST .../attachments, ``purpose=notebook``,
plugin attachments), puis rattachés à l'entrée qui les montre (plugin notebook, testé dans
``tests/plugins/notebook``) - c'est le seul chemin du front, les anciennes routes « pièces jointes »
d'une expérience ont disparu. Les octets restent servis par attachments. Le téléversement lui-même
est testé dans test_uploads.py.
"""

from __future__ import annotations

from support.experiments import launch
from support.http import PNG_1PX
from support.microprojects import signup_with_microproject
from support.notebook import add_manual, upload_notebook_file


def test_a_notebook_image_is_served_by_attachments(client):
    slug = signup_with_microproject(client, "attach@example.com")
    launched = launch(client, slug)
    image_id = upload_notebook_file(client, slug, "sem.png")

    [measurement] = add_manual(client, slug, launched["id"], "SEM du bord", measurements=[{"attachments": [image_id]}])["measurements"]
    [image] = measurement["attachments"]
    assert image["url"] == f"/api/microprojects/{slug}/attachments/{image_id}/content"
    download = client.get(image["url"])
    assert download.status_code == 200 and download.content == PNG_1PX
    assert download.headers["content-type"] == "image/png"
