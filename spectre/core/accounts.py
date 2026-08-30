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


def update_name(user_id: int, name: str) -> User:
    name = name.strip()
    if not name:
        raise ValueError("le nom ne peut pas être vide")
    with get_conn() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
    user = get_by_id(user_id)
    assert user is not None
    return user


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Change a user's password, verifying ``current_password`` first, and sign them out of every
    session (including the one making this call - the caller re-authenticates after).
    """
    if len(new_password) < 8:
        raise ValueError("le mot de passe doit contenir au moins 8 caractères")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not security.verify_password(current_password, row["password_hash"], row["salt"]):
            raise InvalidCredentialsError("mot de passe actuel incorrect")
        password_hash, salt = security.hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (password_hash, salt, user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_password_reset(user_id: int) -> str:
    token = security.new_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, security.password_reset_expiry()),
        )
    return token


def user_for_reset_token(token: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT users.* FROM password_resets JOIN users ON users.id = password_resets.user_id "
            "WHERE password_resets.token = ? AND password_resets.expires_at > datetime('now')",
            (token,),
        ).fetchone()
    return _user_from_row(row) if row else None


def reset_password(token: str, new_password: str) -> User:
    """Consume a password-reset token: set the new password, delete the token (one-time use) and
    every existing session for that user - the same "sign out everywhere" hygiene as
    :func:`change_password`.
    """
    user = user_for_reset_token(token)
    if user is None:
        raise InvalidCredentialsError("ce lien de réinitialisation est invalide ou a expiré")
    if len(new_password) < 8:
        raise ValueError("le mot de passe doit contenir au moins 8 caractères")
    password_hash, salt = security.hash_password(new_password)
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (password_hash, salt, user.id))
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user.id,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
    return user
