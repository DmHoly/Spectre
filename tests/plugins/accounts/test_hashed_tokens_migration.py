"""Les jetons de session et de réinitialisation passent en empreinte SHA-256 : la migration hache les
lignes d'une base existante, si bien qu'une session ouverte et un lien déjà envoyé restent valides."""

from __future__ import annotations

import dataclasses
import hashlib
import sqlite3

from fastapi.testclient import TestClient

from spectre.kernel.db import run_migrations
from spectre.plugins.accounts import PLUGIN as ACCOUNTS
from spectre.plugins.accounts.security import hash_password


def test_existing_sessions_and_reset_links_survive_the_hashing(data_dir):
    run_migrations([dataclasses.replace(ACCOUNTS, migrations=ACCOUNTS.migrations[:2])])
    password_hash, salt = hash_password("supersecret")
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, salt) VALUES (1, 'old@example.com', 'Old', ?, ?)",
        (password_hash, salt),
    )
    conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES ('clear-session', 1, '2999-01-01 00:00:00')")
    conn.execute("INSERT INTO password_resets (token, user_id, expires_at) VALUES ('clear-reset', 1, '2999-01-01 00:00:00')")
    conn.commit()
    conn.close()

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:
        conn = sqlite3.connect(data_dir / "spectre.db")
        stored = {row[0] for row in conn.execute("SELECT token_hash FROM sessions UNION SELECT token_hash FROM password_resets")}
        conn.close()
        assert stored == {hashlib.sha256(b"clear-session").hexdigest(), hashlib.sha256(b"clear-reset").hexdigest()}

        client.cookies.set("spectre_session", "clear-session")
        assert client.get("/api/users/me").json()["email"] == "old@example.com"

        response = client.post("/api/password-resets/completions", json={"token": "clear-reset", "password": "nouveaumdp123"})
        assert response.status_code == 204
