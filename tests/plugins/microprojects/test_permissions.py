from __future__ import annotations

from support.accounts import login, signup
from support.microprojects import add_member, create_microproject, members


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


def test_listing_every_microproject_is_admin_only(client):
    signup(client, "boss@example.com")  # le premier compte est admin
    create_microproject(client, "A")
    signup(client, "hand@example.com")
    create_microproject(client, "B")

    assert client.get("/api/microprojects", params={"scope": "all"}).status_code == 403
    login(client, "boss@example.com")
    every = {p["slug"]: (p["role"], p["role_source"]) for p in client.get("/api/microprojects", params={"scope": "all"}).json()}
    # l'admin a le rôle owner partout, même dans « B » dont il n'est pas membre
    assert every == {"a": ("owner", "membership"), "b": ("owner", "admin")}
