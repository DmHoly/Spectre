"""User accounts and sessions: the thin data-access layer over the ``users``/``sessions`` tables
(see :mod:`spectre.plugins.accounts.migrations`). Kept separate from permissions/microprojects - this
module only knows about one user at a time, never about what they're allowed to do.

The rules an address and a password follow live here and only here (:func:`normalize_email`,
:func:`check_password`). Session and password-reset tokens are stored hashed
(:func:`~spectre.plugins.accounts.security.hash_token`): the functions below take and return the
clear token, and hash it themselves.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ...kernel import mail
from ...kernel.db import get_conn
from ...kernel.errors import Conflict, InvalidInput, NotFound, Unauthorized
from . import security

MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    is_admin: bool = False


def _user_from_row(row: sqlite3.Row) -> User:
    keys = row.keys()
    return User(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        is_admin=bool(row["is_admin"]) if "is_admin" in keys else False,
    )


def normalize_email(email: str) -> str:
    """The form an address is stored and looked up in: trimmed, lower-case."""
    return email.strip().lower()


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInput(f"le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères", code="weak_password")


def register(email: str, password: str, name: str) -> User:
    email = normalize_email(email)
    if not email or "@" not in email:
        raise InvalidInput("adresse e-mail invalide", code="invalid_email")
    check_password(password)
    name = name.strip() or email.split("@")[0]
    password_hash, salt = security.hash_password(password)
    with get_conn() as conn:
        # the very first account is the admin (manages the strategy layer) - there is otherwise no
        # way to bootstrap one; `spectre admin <email>` promotes others later.
        first_account = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is None
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, name, password_hash, salt, is_admin) VALUES (?, ?, ?, ?, ?)",
                (email, name, password_hash, salt, 1 if first_account else 0),
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"un compte existe déjà avec l'adresse {email!r}", code="email_taken") from exc
        return User(id=cursor.lastrowid, email=email, name=name, is_admin=first_account)


def set_admin(email: str, is_admin: bool) -> User:
    """Promote/demote an account to the strategy-layer admin role (see ``management_areas``)."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
        if row is None:
            raise NotFound(f"aucun compte avec l'adresse {email!r}")
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (1 if is_admin else 0, row["id"]))
        return User(id=row["id"], email=row["email"], name=row["name"], is_admin=is_admin)


def authenticate(email: str, password: str) -> User:
    """The account behind these credentials - 422 otherwise (never 401, which means « no session »
    to the front and sends it to the login page)."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
    if row is None or not security.verify_password(password, row["password_hash"], row["salt"]):
        raise InvalidInput("e-mail ou mot de passe incorrect", code="invalid_credentials")
    return _user_from_row(row)


def get_by_id(user_id: int) -> User | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


def get_by_email(email: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
    return _user_from_row(row) if row else None


def create_session(user_id: int) -> tuple[str, str]:
    """Open a session: ``(token, expires_at)``. Sessions that have expired are purged on the way -
    nothing else ever deletes them."""
    token = security.new_session_token()
    expires_at = security.session_expiry()
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (security.hash_token(token), user_id, expires_at),
        )
    return token, expires_at


def session(token: str | None) -> tuple[User, str]:
    """The live session of ``token``: ``(user, expires_at)`` - :class:`Unauthorized` (401, the one
    status reserved for « no session ») without a token, or for an unknown or expired one."""
    if not token:
        raise Unauthorized("connexion requise")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT users.*, sessions.expires_at AS session_expires_at FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token_hash = ? AND sessions.expires_at > datetime('now')",
            (security.hash_token(token),),
        ).fetchone()
    if row is None:
        raise Unauthorized("connexion requise")
    return _user_from_row(row), row["session_expires_at"]


def delete_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (security.hash_token(token),))


def update_name(user_id: int, name: str) -> User:
    name = name.strip()
    if not name:
        raise InvalidInput("le nom ne peut pas être vide")
    with get_conn() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
    user = get_by_id(user_id)
    assert user is not None
    return user


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Change a user's password, verifying ``current_password`` first, and sign them out of every
    session (including the one making this call - the caller re-authenticates after). A wrong
    current password is a 422: the session itself is fine, the front must not log the user out.
    """
    check_password(new_password)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not security.verify_password(current_password, row["password_hash"], row["salt"]):
            raise InvalidInput("mot de passe actuel incorrect", code="invalid_current_password")
        password_hash, salt = security.hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (password_hash, salt, user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_password_reset(user_id: int) -> str:
    """A one-hour reset token for ``user_id`` (returned in clear, stored hashed). Expired requests
    are purged on the way."""
    token = security.new_token()
    with get_conn() as conn:
        conn.execute("DELETE FROM password_resets WHERE expires_at <= datetime('now')")
        conn.execute(
            "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (security.hash_token(token), user_id, security.password_reset_expiry()),
        )
    return token


def send_password_reset(email: str) -> None:
    """E-mail a reset link to ``email`` if it has an account - and do nothing otherwise, so that
    the caller (which answers the same either way) never tells whether the account exists. Run
    after the response (a background task): the time it takes says nothing either.
    """
    user = get_by_email(email)
    if user is None:
        return
    token = create_password_reset(user.id)
    link = f"{mail.base_url()}/reinitialiser?token={token}"
    mail.send_email(
        user.email,
        "Réinitialiser votre mot de passe Spectre",
        f"Bonjour {user.name},\n\n"
        f"Pour choisir un nouveau mot de passe, ouvrez ce lien (valable 1 heure) :\n{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.",
    )


def user_for_reset_token(token: str) -> User | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT users.* FROM password_resets JOIN users ON users.id = password_resets.user_id "
            "WHERE password_resets.token_hash = ? AND password_resets.expires_at > datetime('now')",
            (security.hash_token(token),),
        ).fetchone()
    return _user_from_row(row) if row else None


def reset_password(token: str, new_password: str) -> User:
    """Consume a password-reset token: set the new password, delete the token (one-time use) and
    every existing session for that user - the same "sign out everywhere" hygiene as
    :func:`change_password`.
    """
    user = user_for_reset_token(token)
    if user is None:
        raise InvalidInput("ce lien de réinitialisation est invalide ou a expiré", code="invalid_token")
    check_password(new_password)
    password_hash, salt = security.hash_password(new_password)
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (password_hash, salt, user.id))
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user.id,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
    return user
