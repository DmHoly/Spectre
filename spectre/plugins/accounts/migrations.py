"""Les tables du plugin accounts : comptes, sessions, jetons de réinitialisation."""

from __future__ import annotations

import os
import sqlite3

from ...kernel.db import column_names, execute_script
from ...kernel.plugin import Migration
from .security import hash_password, hash_token

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
"""


def _initial(conn: sqlite3.Connection) -> None:
    execute_script(conn, SCHEMA)
    if "is_admin" not in column_names(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")


def _promote_first_admin(conn: sqlite3.Connection) -> None:
    """Une base d'avant le rôle administrateur n'en a aucun : son premier compte le devient. Une
    seule fois - un administrateur révoqué depuis (``spectre admin --revoke``) ne l'est plus au
    redémarrage suivant. Sur une base neuve, c'est :func:`spectre.plugins.accounts.service.register`
    qui fait du premier compte l'administrateur."""
    has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    has_admin = conn.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone() is not None
    if has_users and not has_admin:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)")


def _hash_tokens(conn: sqlite3.Connection) -> None:
    """Les jetons de session et de réinitialisation ne sont plus gardés qu'en empreinte SHA-256
    (colonne ``token_hash``) : les lignes existantes sont hachées sur place, si bien que les
    sessions ouvertes et les liens déjà envoyés restent valides."""
    for table in ("sessions", "password_resets"):
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN token TO token_hash")
        for (token,) in conn.execute(f"SELECT token_hash FROM {table}").fetchall():
            conn.execute(f"UPDATE {table} SET token_hash = ? WHERE token_hash = ?", (hash_token(token), token))


def _must_change_password(conn: sqlite3.Connection) -> None:
    """Un compte dont l'administrateur a réinitialisé le mot de passe (ou le compte initial) doit en
    choisir un nouveau à sa prochaine connexion."""
    conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")


def _bootstrap_admin(conn: sqlite3.Connection) -> None:
    """Sur une base neuve, le compte administrateur initial décrit par ``SPECTRE_INITIAL_ADMIN``
    (``identifiant:mot de passe``, posé par l'image Docker) : il n'y a sinon aucun moyen d'ouvrir la
    gestion des utilisateurs. Son mot de passe est à changer à la première connexion. Une seule
    fois, et seulement si aucun compte n'existe."""
    raw = os.environ.get("SPECTRE_INITIAL_ADMIN", "")
    login, _, password = raw.partition(":")
    login = login.strip().lower()
    if not login or not password or conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
        return
    password_hash, salt = hash_password(password)
    conn.execute(
        "INSERT INTO users (email, name, password_hash, salt, is_admin, must_change_password) VALUES (?, ?, ?, ?, 1, 1)",
        (login, login, password_hash, salt),
    )


MIGRATIONS = (
    Migration("0001_initial", _initial),
    Migration("0002_first_admin", _promote_first_admin),
    Migration("0003_hashed_tokens", _hash_tokens),
    Migration("0004_must_change_password", _must_change_password),
    Migration("0005_bootstrap_admin", _bootstrap_admin),
)
