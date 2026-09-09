from __future__ import annotations


def _register(client, email, name):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})


def _login(client, email):
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": email, "password": "supersecret"})


def test_viewer_cannot_manage_members(client):
    _register(client, "owner@example.com", "Owner")
    microproject = client.post("/api/microprojets", json={"name": "Projet A"}).json()
    slug = microproject["slug"]

    _register(client, "viewer@example.com", "Viewer")

    _login(client, "owner@example.com")
    add = client.post(f"/api/microprojets/{slug}/members", json={"email": "viewer@example.com", "role": "viewer"})
    assert add.status_code == 201

    _login(client, "viewer@example.com")
    assert client.get(f"/api/microprojets/{slug}").status_code == 200
    forbidden = client.post(f"/api/microprojets/{slug}/members", json={"email": "owner@example.com", "role": "viewer"})
    assert forbidden.status_code == 403


def test_editor_can_be_listed_but_not_manage_members(client):
    _register(client, "owner2@example.com", "Owner2")
    microproject = client.post("/api/microprojets", json={"name": "Projet B"}).json()
    slug = microproject["slug"]

    _register(client, "editor@example.com", "Editor")

    _login(client, "owner2@example.com")
    client.post(f"/api/microprojets/{slug}/members", json={"email": "editor@example.com", "role": "editor"})

    _login(client, "editor@example.com")
    members = client.get(f"/api/microprojets/{slug}/members").json()
    assert any(m["email"] == "editor@example.com" for m in members)
    forbidden = client.post(f"/api/microprojets/{slug}/members", json={"email": "owner2@example.com", "role": "editor"})
    assert forbidden.status_code == 403


def test_non_member_cannot_see_microproject(client):
    _register(client, "owner3@example.com", "Owner3")
    microproject = client.post("/api/microprojets", json={"name": "Projet C"}).json()
    slug = microproject["slug"]

    _register(client, "stranger@example.com", "Stranger")
    response = client.get(f"/api/microprojets/{slug}")
    assert response.status_code == 403
