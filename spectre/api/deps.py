"""Shared FastAPI dependencies: who is making this request, and (see :mod:`spectre.api.projects`
and :mod:`spectre.core.permissions` once a project is involved) what they're allowed to do here.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..core import accounts
from ..core.accounts import User
from ..core.security import SESSION_COOKIE


def get_current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = accounts.user_for_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="connexion requise")
    return user


def get_current_user_optional(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    return accounts.user_for_session(token) if token else None
