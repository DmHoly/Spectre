"""User accounts and sessions: the thin data-access layer over the ``users``/``sessions`` tables
in :mod:`spectre.core.db`. Kept separate from permissions/projects - this module only knows about
one user at a time, never about what they're allowed to do.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import security
from .db import get_conn


class EmailAlreadyUsedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str


def _user_from_row(row: sqlite3.Row) -> User:
    return User(id=row["id"], email=row["email"], name=row["name"])


def register(email: str, password: str, name: str) -> User:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("adresse e-mail invalide")
    if len(password) < 8:
        raise ValueError("le mot de passe doit contenir au moins 8 caractères")
    name = name.strip() or email.split("@")[0]
    password_hash, salt = security.hash_password(password)
    with get_conn() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, name, password_hash, salt) VALUES (?, ?, ?, ?)",
                (email, name, password_hash, salt),
            )
        except sqlite3.IntegrityError as exc:
            raise EmailAlreadyUsedError(f"un compte existe déjà avec l'adresse {email!r}") from exc
        return User(id=cursor.lastrowid, email=email, name=name)


def authenticate(email: str, password: str) -> User:
    email = email.strip().lower()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not security.verify_password(password, row["password_hash"], row["salt"]):
        raise InvalidCredentialsError("e-mail ou mot de passe incorrect")
    return _user_from_row(row)


def get_by_id(user_id: int) -> User | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


def get_by_email(email: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return _user_from_row(row) if row else None


def create_session(user_id: int) -> str:
    token = security.new_session_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, security.session_expiry()),
        )
    return token


def user_for_session(token: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token = ? AND sessions.expires_at > datetime('now')",
            (token,),
        ).fetchone()
    return _user_from_row(row) if row else None


def delete_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
