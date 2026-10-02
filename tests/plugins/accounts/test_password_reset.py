from __future__ import annotations

from support.accounts import link_token, logout, signup


def test_forgot_password_always_returns_ok(client, outbox):
    signup(client, "reset@example.com", name="R")
    logout(client)

    # unknown address: still 200, no leak - and nothing sent
    response = client.post("/api/auth/mot-de-passe-oublie", json={"email": "unknown@example.com"})
    assert response.status_code == 200
    assert outbox == []

    response = client.post("/api/auth/mot-de-passe-oublie", json={"email": "reset@example.com"})
    assert response.status_code == 200
    assert [email.to for email in outbox] == ["reset@example.com"]


def test_reset_password_flow(client, outbox):
    signup(client, "reset2@example.com", name="R2")
    logout(client)

    client.post("/api/auth/mot-de-passe-oublie", json={"email": "reset2@example.com"})
    [email] = outbox
    assert "/reinitialiser?token=" in email.body
    token = link_token(email.body, "token")

    response = client.post("/api/auth/reinitialiser", json={"token": token, "password": "nouveaumdp123"})
    assert response.status_code == 200

    # old password no longer works, new one does
    assert client.post("/api/auth/login", json={"email": "reset2@example.com", "password": "supersecret"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "reset2@example.com", "password": "nouveaumdp123"}).status_code == 200

    # the token is one-time use
    response = client.post("/api/auth/reinitialiser", json={"token": token, "password": "encoreunautre123"})
    assert response.status_code == 400


def test_without_smtp_the_message_is_logged_instead(client, caplog):
    # no SPECTRE_SMTP_HOST (conftest clears it): dev mode logs the link rather than failing
    signup(client, "reset3@example.com", name="R3")
    logout(client)
    with caplog.at_level("WARNING", logger="spectre.email"):
        client.post("/api/auth/mot-de-passe-oublie", json={"email": "reset3@example.com"})
    assert "/reinitialiser?token=" in "\n".join(r.message for r in caplog.records)


def test_reset_password_rejects_invalid_token(client):
    response = client.post("/api/auth/reinitialiser", json={"token": "not-a-real-token", "password": "supersecret123"})
    assert response.status_code == 400
