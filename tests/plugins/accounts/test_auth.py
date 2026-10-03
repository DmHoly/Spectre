from __future__ import annotations

import hashlib
import sqlite3

from support.accounts import PASSWORD, login, logout, signup


def test_register_login_me_logout(client):
    response = client.post("/api/users", json={"email": "ana@example.com", "password": "supersecret", "name": "Ana"})
    assert response.status_code == 201
    assert response.headers["location"] == "/api/users/me"
    assert response.json()["email"] == "ana@example.com"

    # the new account leaves signed in
    me = client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Ana"

    response = client.delete("/api/sessions/current")
    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/users/me").status_code == 401

    response = client.post("/api/sessions", json={"email": "ana@example.com", "password": "supersecret"})
    assert response.status_code == 201
    assert response.headers["location"] == "/api/sessions/current"
    assert response.json()["user"]["email"] == "ana@example.com"
    assert response.json()["expires_at"]
    assert client.get("/api/users/me").status_code == 200


def test_logout_without_session_is_a_204(client):
    response = client.delete("/api/sessions/current")
    assert response.status_code == 204


def test_register_rejects_duplicate_email(client):
    signup(client, "b@example.com", name="B")
    response = client.post("/api/users", json={"email": " B@Example.com ", "password": "supersecret2", "name": "B2"})
    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


def test_register_rejects_short_password(client):
    response = client.post("/api/users", json={"email": "c@example.com", "password": "short", "name": "C"})
    assert response.status_code == 422
    assert response.json()["code"] == "weak_password"


def test_register_rejects_an_invalid_email(client):
    response = client.post("/api/users", json={"email": "pas-une-adresse", "password": "supersecret", "name": "C"})
    assert response.status_code == 422


def test_login_rejects_wrong_password_without_401(client):
    signup(client, "d@example.com", name="D")
    logout(client)
    # 401 means « no session » to the front (it redirects to the login page): wrong credentials are a 422
    response = client.post("/api/sessions", json={"email": "d@example.com", "password": "wrong-password"})
    assert response.status_code == 422
    assert response.json() == {"detail": "e-mail ou mot de passe incorrect", "code": "invalid_credentials"}
    response = client.post("/api/sessions", json={"email": "inconnu@example.com", "password": "wrong-password"})
    assert response.status_code == 422


def test_email_is_normalized_everywhere(client):
    signup(client, "  Mixed@Example.COM ", name="M")
    logout(client)
    assert login(client, "MIXED@example.com")["email"] == "mixed@example.com"


def test_me_requires_session(client):
    assert client.get("/api/users/me").status_code == 401


def test_pages_are_served(client):
    for path in ("/connexion", "/inscription", "/"):
        assert client.get(path).status_code == 200


def _session_rows(data_dir):
    conn = sqlite3.connect(data_dir / "spectre.db")
    try:
        return conn.execute("SELECT token_hash, expires_at FROM sessions").fetchall()
    finally:
        conn.close()


def test_session_token_is_stored_hashed(client, data_dir):
    signup(client, "hash@example.com", name="H")
    token = client.cookies.get("spectre_session")
    [(stored, _)] = _session_rows(data_dir)
    assert stored != token
    assert stored == hashlib.sha256(token.encode()).hexdigest()


def test_expired_sessions_are_purged_when_a_session_opens(client, data_dir):
    signup(client, "purge@example.com", name="P")
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute("UPDATE sessions SET expires_at = '2000-01-01 00:00:00'")
    conn.commit()
    conn.close()
    assert client.get("/api/users/me").status_code == 401

    login(client, "purge@example.com")
    [(_, expires_at)] = _session_rows(data_dir)
    assert expires_at > "2000-01-01 00:00:00"


def _cookie_header(response) -> str:
    [header] = [value for name, value in response.headers.multi_items() if name == "set-cookie"]
    return header.lower()


def test_session_cookie_is_not_secure_on_plain_http(client):
    response = client.post("/api/users", json={"email": "http@example.com", "password": PASSWORD})
    header = _cookie_header(response)
    assert "httponly" in header and "samesite=lax" in header
    assert "secure" not in header


def test_session_cookie_is_secure_behind_https(client, monkeypatch):
    monkeypatch.setenv("SPECTRE_BASE_URL", "https://spectre.example.com")
    response = client.post("/api/users", json={"email": "https@example.com", "password": PASSWORD})
    assert "secure" in _cookie_header(response)


def test_session_cookie_secure_can_be_forced_either_way(client, monkeypatch):
    monkeypatch.setenv("SPECTRE_COOKIE_SECURE", "1")
    response = client.post("/api/users", json={"email": "on@example.com", "password": PASSWORD})
    assert "secure" in _cookie_header(response)

    monkeypatch.setenv("SPECTRE_BASE_URL", "https://spectre.example.com")
    monkeypatch.setenv("SPECTRE_COOKIE_SECURE", "0")
    logout(client)
    response = client.post("/api/users", json={"email": "off@example.com", "password": PASSWORD})
    assert "secure" not in _cookie_header(response)
