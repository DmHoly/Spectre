"""Who can do what in a microproject: ``viewer`` reads, ``editor`` also creates/evolves/concludes
experiments and manages step presets, ``owner`` also manages membership. Follow and StructureForge have
no notion of any of this - it lives entirely here, as a FastAPI dependency that resolves the
microproject from the URL and checks the caller's membership before the route body ever runs.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..accounts.deps import current_user
from ..accounts.service import User
from .service import ROLE_ORDER, Microproject, MicroprojectNotFoundError, get_by_slug, role_for


def get_microproject(slug: str) -> Microproject:
    try:
        return get_by_slug(slug)
    except MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def require_role(min_role: str):
    """A FastAPI dependency: 403s unless the current user's role in this microproject is at least
    ``min_role`` (``viewer`` < ``editor`` < ``owner``). Returns the resolved :class:`Microproject` on
    success, so a route can depend on this alone instead of also depending on :func:`get_microproject`.

    The caller is identified first (FastAPI resolves sub-dependencies in parameter order): an
    anonymous request gets its 401 before the microproject is even looked up, rather than a 404
    telling it which slugs exist.
    """

    def dependency(user: User = Depends(current_user), microproject: Microproject = Depends(get_microproject)) -> Microproject:
        role = role_for(microproject.id, user.id)
        if role is None or ROLE_ORDER[role] < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
        return microproject

    return dependency
