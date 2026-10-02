from __future__ import annotations

from support.accounts import login, signup
from support.microprojects import add_member, create_microproject


def test_viewer_cannot_manage_members(client):
    signup(client, "owner@example.com", name="Owner")
    slug = create_microproject(client, "Projet A")["slug"]

    signup(client, "viewer@example.com", name="Viewer")

    login(client, "owner@example.com")
    add = client.post(f"/api/microprojets/{slug}/members", json={"email": "viewer@example.com", "role": "viewer"})
    assert add.status_code == 201

    login(client, "viewer@example.com")
    assert client.get(f"/api/microprojets/{slug}").status_code == 200
    forbidden = client.post(f"/api/microprojets/{slug}/members", json={"email": "owner@example.com", "role": "viewer"})
    assert forbidden.status_code == 403


def test_editor_can_be_listed_but_not_manage_members(client):
    signup(client, "owner2@example.com", name="Owner2")
    slug = create_microproject(client, "Projet B")["slug"]

    signup(client, "editor@example.com", name="Editor")

    login(client, "owner2@example.com")
    add_member(client, slug, "editor@example.com", "editor")

    login(client, "editor@example.com")
    members = client.get(f"/api/microprojets/{slug}/members").json()
    assert any(m["email"] == "editor@example.com" for m in members)
    forbidden = client.post(f"/api/microprojets/{slug}/members", json={"email": "owner2@example.com", "role": "editor"})
    assert forbidden.status_code == 403


def test_non_member_cannot_see_microproject(client):
    signup(client, "owner3@example.com", name="Owner3")
    slug = create_microproject(client, "Projet C")["slug"]

    signup(client, "stranger@example.com", name="Stranger")
    response = client.get(f"/api/microprojets/{slug}")
    assert response.status_code == 403
