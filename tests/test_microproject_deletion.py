from __future__ import annotations


def test_owner_can_delete_microproject(client):
    client.post("/api/auth/register", json={"email": "del1@example.com", "password": "supersecret", "name": "D1"})
    microproject = client.post("/api/microprojets", json={"name": "Projet a supprimer"}).json()
    slug = microproject["slug"]

    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Projet+a+supprimer")
    assert response.status_code == 200

    assert client.get(f"/api/microprojets/{slug}").status_code == 404
    assert not any(p["slug"] == slug for p in client.get("/api/microprojets").json())


def test_delete_requires_matching_name(client):
    client.post("/api/auth/register", json={"email": "del2@example.com", "password": "supersecret", "name": "D2"})
    microproject = client.post("/api/microprojets", json={"name": "Nom exact"}).json()
    slug = microproject["slug"]

    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Mauvais+nom")
    assert response.status_code == 422
    assert client.get(f"/api/microprojets/{slug}").status_code == 200


def test_editor_cannot_delete_microproject(client):
    client.post("/api/auth/register", json={"email": "del3@example.com", "password": "supersecret", "name": "D3"})
    microproject = client.post("/api/microprojets", json={"name": "Projet protege"}).json()
    slug = microproject["slug"]

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "del3editor@example.com", "password": "supersecret", "name": "E3"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "del3@example.com", "password": "supersecret"})
    client.post(f"/api/microprojets/{slug}/members", json={"email": "del3editor@example.com", "role": "editor"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "del3editor@example.com", "password": "supersecret"})
    response = client.delete(f"/api/microprojets/{slug}?confirm_name=Projet+protege")
    assert response.status_code == 403
