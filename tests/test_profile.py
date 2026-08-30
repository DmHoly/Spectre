from __future__ import annotations


def test_update_profile_name(client):
    client.post("/api/auth/register", json={"email": "profile@example.com", "password": "supersecret", "name": "Ancien Nom"})
    response = client.request("PUT", "/api/auth/me", json={"name": "Nouveau Nom"})
    assert response.status_code == 200
    assert response.json()["name"] == "Nouveau Nom"
    assert client.get("/api/auth/me").json()["name"] == "Nouveau Nom"


def test_update_profile_rejects_empty_name(client):
    client.post("/api/auth/register", json={"email": "profile2@example.com", "password": "supersecret", "name": "X"})
    response = client.request("PUT", "/api/auth/me", json={"name": "   "})
    assert response.status_code == 422


def test_change_password_requires_current_password(client):
    client.post("/api/auth/register", json={"email": "pw@example.com", "password": "supersecret", "name": "P"})
    response = client.post("/api/auth/mot-de-passe", json={"current_password": "wrong", "new_password": "nouveaumdp123"})
    assert response.status_code == 401


def test_change_password_signs_out_everywhere(client):
    client.post("/api/auth/register", json={"email": "pw2@example.com", "password": "supersecret", "name": "P2"})
    response = client.post("/api/auth/mot-de-passe", json={"current_password": "supersecret", "new_password": "nouveaumdp123"})
    assert response.status_code == 200

    # the very session that changed the password is now dead too
    assert client.get("/api/auth/me").status_code == 401

    assert client.post("/api/auth/login", json={"email": "pw2@example.com", "password": "supersecret"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "pw2@example.com", "password": "nouveaumdp123"}).status_code == 200
