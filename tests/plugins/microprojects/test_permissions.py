from __future__ import annotations

from support.accounts import login, signup
from support.microprojects import add_member, create_microproject, members


def test_viewer_cannot_manage_members(client):
    signup(client, "owner@example.com", name="Owner")
    slug = create_microproject(client, "Projet A")["slug"]

    viewer = signup(client, "viewer@example.com", name="Viewer")

    login(client, "owner@example.com")
    add_member(client, slug, "viewer@example.com", "viewer")

    login(client, "viewer@example.com")
    assert client.get(f"/api/microprojects/{slug}").status_code == 200
    url = f"/api/microprojects/{slug}"
    assert client.post(f"{url}/members", json={"email": "owner@example.com", "role": "viewer"}).status_code == 403
    assert client.patch(f"{url}/members/{viewer['id']}", json={"role": "owner"}).status_code == 403
    assert client.delete(f"{url}/members/{viewer['id']}").status_code == 403
    assert client.get(f"{url}/invitations").status_code == 403
    assert client.post(f"{url}/invitations", json={"email": "x@example.com", "role": "viewer"}).status_code == 403


def test_editor_can_be_listed_but_not_manage_members(client):
    signup(client, "owner2@example.com", name="Owner2")
    slug = create_microproject(client, "Projet B")["slug"]

    signup(client, "editor@example.com", name="Editor")

    login(client, "owner2@example.com")
    add_member(client, slug, "editor@example.com", "editor")

    login(client, "editor@example.com")
    assert any(m["email"] == "editor@example.com" for m in members(client, slug))
    forbidden = client.post(f"/api/microprojects/{slug}/members", json={"email": "owner2@example.com", "role": "editor"})
    assert forbidden.status_code == 403


def test_non_member_cannot_see_microproject(client):
    signup(client, "owner3@example.com", name="Owner3")
    slug = create_microproject(client, "Projet C")["slug"]

    signup(client, "stranger@example.com", name="Stranger")
    response = client.get(f"/api/microprojects/{slug}")
    assert response.status_code == 403
    assert client.get(f"/api/microprojects/{slug}/members").status_code == 403


def test_listing_every_microproject_is_admin_only(client):
    signup(client, "boss@example.com")  # le premier compte est admin
    create_microproject(client, "A")
    signup(client, "hand@example.com")
    create_microproject(client, "B")

    assert client.get("/api/microprojects", params={"scope": "all"}).status_code == 403
    login(client, "boss@example.com")
    every = {p["slug"]: p["role"] for p in client.get("/api/microprojects", params={"scope": "all"}).json()}
    assert every == {"a": "owner", "b": None}  # le rôle de l'admin, qui n'est pas membre de « B »
