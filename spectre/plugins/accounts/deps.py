"""Shared FastAPI dependencies: who is making this request (:func:`current_user`) and whether they
are a strategy-layer admin (:func:`require_admin`). What they may do inside a microproject is
:func:`spectre.plugins.microprojects.deps.require_role`.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from ...kernel.errors import Forbidden
from . import service as accounts
from .security import SESSION_COOKIE
from .service import User


def current_user(request: Request) -> User:
    """The signed-in user - 401 otherwise, the one status reserved for « no session »."""
    token = request.cookies.get(SESSION_COOKIE)
    user = accounts.user_for_session(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="connexion requise")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """A FastAPI dependency: 403s unless the caller is a strategy-layer admin
    (``users.is_admin``). Used by the management-area write routes - everything else stays
    microproject-scoped through :func:`spectre.plugins.microprojects.deps.require_role`.
    """
    if not user.is_admin:
        raise Forbidden("action réservée à un administrateur")
    return user
