from __future__ import annotations

from support.http import assert_handler_404
from support.microprojects import delete_microproject, get_microproject, join_as, list_microprojects, signup_with_microproject


def test_owner_can_delete_microproject(client, data_dir):
    slug = signup_with_microproject(client, "del1@example.com", "Projet a supprimer", name="D1")
    assert (data_dir / "microprojects" / slug).is_dir()

    response = delete_microproject(client, slug, "Projet a supprimer")
    assert response.status_code == 204 and response.content == b""

    assert_handler_404(client.get(f"/api/microprojects/{slug}"))
    assert list_microprojects(client) == []
    assert not (data_dir / "microprojects" / slug).exists()


def test_delete_requires_matching_name(client):
    slug = signup_with_microproject(client, "del2@example.com", "Nom exact", name="D2")

    response = delete_microproject(client, slug, "Mauvais nom")
    assert response.status_code == 422 and response.json()["code"] == "confirm_name_mismatch"
    assert get_microproject(client, slug)["name"] == "Nom exact"


def test_editor_cannot_delete_microproject(client):
    slug = signup_with_microproject(client, "del3@example.com", "Projet protege", name="D3")

    join_as(client, slug, "del3editor@example.com", owner="del3@example.com", role="editor", name="E3")
    assert delete_microproject(client, slug, "Projet protege").status_code == 403
