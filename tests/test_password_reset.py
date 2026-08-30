from __future__ import annotations

import logging


def test_forgot_password_always_returns_ok(client):
    client.post("/api/auth/register", json={"email": "reset@example.com", "password": "supersecret", "name": "R"})
    client.post("/api/auth/logout")

    # unknown address: still 200, no leak
    response = client.post("/api/auth/mot-de-passe-oublie", json={"email": "unknown@example.com"})
    assert response.status_code == 200

    response = client.post("/api/auth/mot-de-passe-oublie", json={"email": "reset@example.com"})
    assert response.status_code == 200


def test_reset_password_flow(client, caplog):
    client.post("/api/auth/register", json={"email": "reset2@example.com", "password": "supersecret", "name": "R2"})
    client.post("/api/auth/logout")

    with caplog.at_level(logging.WARNING, logger="spectre.email"):
        client.post("/api/auth/mot-de-passe-oublie", json={"email": "reset2@example.com"})

    # dev-mode: no SMTP configured, so the reset link was logged instead of e-mailed
    log_text = "\n".join(r.message for r in caplog.records)
    assert "/reinitialiser?token=" in log_text
    token = log_text.split("token=")[1].split()[0].strip()

    response = client.post("/api/auth/reinitialiser", json={"token": token, "password": "nouveaumdp123"})
    assert response.status_code == 200

    # old password no longer works, new one does
    assert client.post("/api/auth/login", json={"email": "reset2@example.com", "password": "supersecret"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "reset2@example.com", "password": "nouveaumdp123"}).status_code == 200

    # the token is one-time use
    response = client.post("/api/auth/reinitialiser", json={"token": token, "password": "encoreunautre123"})
    assert response.status_code == 400


def test_reset_password_rejects_invalid_token(client):
    response = client.post("/api/auth/reinitialiser", json={"token": "not-a-real-token", "password": "supersecret123"})
    assert response.status_code == 400
