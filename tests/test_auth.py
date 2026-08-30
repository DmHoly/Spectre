from __future__ import annotations


def test_register_login_me_logout(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "ana@example.com", "password": "supersecret", "name": "Ana"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "ana@example.com"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Ana"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    login = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "supersecret"})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_register_rejects_duplicate_email(client):
    client.post("/api/auth/register", json={"email": "b@example.com", "password": "supersecret", "name": "B"})
    response = client.post("/api/auth/register", json={"email": "b@example.com", "password": "supersecret2", "name": "B2"})
    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post("/api/auth/register", json={"email": "c@example.com", "password": "short", "name": "C"})
    assert response.status_code == 422


def test_login_rejects_wrong_password(client):
    client.post("/api/auth/register", json={"email": "d@example.com", "password": "supersecret", "name": "D"})
    response = client.post("/api/auth/login", json={"email": "d@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_me_requires_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_pages_are_served(client):
    for path in ("/connexion", "/inscription", "/"):
        assert client.get(path).status_code == 200
