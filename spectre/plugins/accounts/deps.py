"""Shared FastAPI dependencies: who is making this request (:func:`current_user`) and whether they
are a strategy-layer admin (:func:`require_admin`). What they may do inside a microproject is
:func:`spectre.plugins.microprojects.deps.require_role`.
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...kernel.errors import Forbidden
from . import service as accounts
from .security import SESSION_COOKIE
from .service import User


def current_user_unrestricted(request: Request) -> User:
    """The signed-in user, even one who still has to choose a new password - for the few routes that
    let them do exactly that (read their profile, change the password), and for a redirect route
    that only needs to know whether there is a session."""
    user, _expires_at = accounts.session(request.cookies.get(SESSION_COOKIE))
    return user


def current_user(user: User = Depends(current_user_unrestricted)) -> User:
    """The signed-in user - 401 otherwise, the one status reserved for « no session ». An account
    whose password was reset by an administrator gets 403 ``password_change_required`` everywhere
    until it has chosen a new one (the front sends it to its profile)."""
    if user.must_change_password:
        raise Forbidden("vous devez choisir un nouveau mot de passe", code="password_change_required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """A FastAPI dependency: 403s unless the caller is a strategy-layer admin
    (``users.is_admin``). Used by the management-area write routes - everything else stays
    microproject-scoped through :func:`spectre.plugins.microprojects.deps.require_role`.
    """
    if not user.is_admin:
        raise Forbidden("action réservée à un administrateur")
    return user
