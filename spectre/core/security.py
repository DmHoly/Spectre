"""Password hashing and session tokens - stdlib only (``hashlib.pbkdf2_hmac`` + ``secrets``), no
extra dependency such as passlib, bcrypt or PyJWT for what is a small, self-hosted user base.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

SESSION_COOKIE = "spectre_session"
SESSION_LIFETIME = timedelta(days=14)
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, *, salt: str | None = None) -> tuple[str, str]:
    """Return ``(password_hash, salt)``, both hex-encoded. Pass ``salt`` back in to verify a
    password against an existing hash instead of generating a fresh one.
    """
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt=salt)
    return secrets.compare_digest(candidate, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sql_datetime(dt: datetime) -> str:
    """``YYYY-MM-DD HH:MM:SS`` in UTC - the same format/timezone SQLite's own ``datetime('now')``
    produces, so ``expires_at`` stays directly comparable to it in SQL (``>``, string-ordered).
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def session_expiry() -> str:
    return _sql_datetime(utcnow() + SESSION_LIFETIME)
