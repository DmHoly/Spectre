"""Who can do what in a microproject: ``viewer`` reads, ``editor`` also creates/evolves/concludes
experiments and manages step presets, ``owner`` also manages membership. Follow and StructureForge have
no notion of any of this - it lives entirely here, as a FastAPI dependency that resolves the
microproject from the URL and checks the caller's membership before the route body ever runs.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..api.deps import get_current_user
from .accounts import User
from .microprojects import ROLE_ORDER, Microproject, MicroprojectNotFoundError, get_by_slug, role_for


def get_microproject(slug: str) -> Microproject:
    try:
        return get_by_slug(slug)
    except MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def require_admin(user: User = Depends(get_current_user)) -> User:
    """A FastAPI dependency: 403s unless the caller is a strategy-layer admin
    (``users.is_admin``). Used by the management-area write routes - everything else stays
    microproject-scoped through :func:`require_role`.
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="action réservée à un administrateur")
    return user


def require_role(min_role: str):
    """A FastAPI dependency: 403s unless the current user's role in this microproject is at least
    ``min_role`` (``viewer`` < ``editor`` < ``owner``). Returns the resolved :class:`Microproject` on
    success, so a route can depend on this alone instead of also depending on :func:`get_microproject`.
    """

    def dependency(microproject: Microproject = Depends(get_microproject), user: User = Depends(get_current_user)) -> Microproject:
        role = role_for(microproject.id, user.id)
        if role is None or ROLE_ORDER[role] < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
        return microproject

    return dependency
