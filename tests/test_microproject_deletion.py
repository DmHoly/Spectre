from __future__ import annotations

from support.http import assert_handler_404
from support.microprojects import join_as, signup_with_microproject


def test_owner_can_delete_microproject(client):
    slug = signup_with_microproject(client, "del1@example.com", "Projet a supprimer", name="D1")

    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Projet+a+supprimer")
    assert response.status_code == 200

    assert_handler_404(client.get(f"/api/microprojets/{slug}"))
    assert not any(p["slug"] == slug for p in client.get("/api/microprojets").json())


def test_delete_requires_matching_name(client):
    slug = signup_with_microproject(client, "del2@example.com", "Nom exact", name="D2")

    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Mauvais+nom")
    assert response.status_code == 422
    assert client.get(f"/api/microprojets/{slug}").status_code == 200


def test_editor_cannot_delete_microproject(client):
    slug = signup_with_microproject(client, "del3@example.com", "Projet protege", name="D3")

    join_as(client, slug, "del3editor@example.com", owner="del3@example.com", role="editor", name="E3")
    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Projet+protege")
    assert response.status_code == 403
