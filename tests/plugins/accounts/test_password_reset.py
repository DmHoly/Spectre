from __future__ import annotations

import hashlib
import sqlite3

from support.accounts import link_token, login, logout, signup


def _request_reset(client, email):
    response = client.post("/api/password-resets", json={"email": email})
    assert response.status_code == 202, response.text
    return response


def test_forgot_password_answers_the_same_whether_or_not_the_account_exists(client, outbox):
    signup(client, "reset@example.com", name="R")
    logout(client)

    # unknown address: the same empty 202, no leak - and nothing sent
    unknown = _request_reset(client, "unknown@example.com")
    assert outbox == []

    known = _request_reset(client, "reset@example.com")
    assert [email.to for email in outbox] == ["reset@example.com"]
    assert unknown.content == known.content == b""


def test_reset_password_flow(client, outbox):
    signup(client, "reset2@example.com", name="R2")
    logout(client)

    _request_reset(client, "  Reset2@Example.com")
    [email] = outbox
    assert "/reinitialiser?token=" in email.body
    token = link_token(email.body, "token")

    response = client.post("/api/password-resets/completions", json={"token": token, "password": "nouveaumdp123"})
    assert response.status_code == 204 and response.content == b""

    # old password no longer works, new one does
    assert client.post("/api/sessions", json={"email": "reset2@example.com", "password": "supersecret"}).status_code == 422
    login(client, "reset2@example.com", "nouveaumdp123")

    # the token is one-time use
    response = client.post("/api/password-resets/completions", json={"token": token, "password": "encoreunautre123"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_token"


def test_reset_signs_out_every_session(client, outbox):
    signup(client, "reset4@example.com", name="R4")
    _request_reset(client, "reset4@example.com")
    token = link_token(outbox[-1].body, "token")
    client.post("/api/password-resets/completions", json={"token": token, "password": "nouveaumdp123"})
    assert client.get("/api/users/me").status_code == 401


def test_reset_password_rejects_a_short_password_and_keeps_the_token(client, outbox):
    signup(client, "reset5@example.com", name="R5")
    logout(client)
    _request_reset(client, "reset5@example.com")
    token = link_token(outbox[-1].body, "token")

    response = client.post("/api/password-resets/completions", json={"token": token, "password": "court"})
    assert response.status_code == 422
    assert response.json()["code"] == "weak_password"
    response = client.post("/api/password-resets/completions", json={"token": token, "password": "nouveaumdp123"})
    assert response.status_code == 204


def test_reset_password_rejects_invalid_token(client):
    response = client.post("/api/password-resets/completions", json={"token": "not-a-real-token", "password": "supersecret123"})
    assert response.status_code == 422
    assert response.json() == {"detail": "ce lien de réinitialisation est invalide ou a expiré", "code": "invalid_token"}


def test_reset_token_is_stored_hashed_and_expired_ones_are_purged(client, outbox, data_dir):
    signup(client, "reset6@example.com", name="R6")
    logout(client)
    _request_reset(client, "reset6@example.com")
    first = link_token(outbox[-1].body, "token")

    conn = sqlite3.connect(data_dir / "spectre.db")
    [(stored,)] = conn.execute("SELECT token_hash FROM password_resets").fetchall()
    assert stored == hashlib.sha256(first.encode()).hexdigest()
    conn.execute("UPDATE password_resets SET expires_at = '2000-01-01 00:00:00'")
    conn.commit()
    conn.close()

    # the expired link no longer works, and asking for a new one purges it
    response = client.post("/api/password-resets/completions", json={"token": first, "password": "nouveaumdp123"})
    assert response.status_code == 422
    _request_reset(client, "reset6@example.com")
    conn = sqlite3.connect(data_dir / "spectre.db")
    rows = conn.execute("SELECT token_hash FROM password_resets").fetchall()
    conn.close()
    assert len(rows) == 1 and rows[0][0] != stored
