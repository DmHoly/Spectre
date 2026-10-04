"""Who can do what in a microproject: ``viewer`` reads, ``editor`` also creates/evolves/concludes
experiments and manages step presets, ``owner`` also manages membership. Follow and StructureForge have
no notion of any of this - it lives entirely here, as a FastAPI dependency that resolves the
microproject from the URL (``{microproject_slug}``) and checks the caller's role before the route
body ever runs. The rule itself is :func:`spectre.plugins.microprojects.service.access`: an admin
and a manager of the µprojet's team are owners, anyone else has the role of their membership.
"""

from __future__ import annotations

from fastapi import Depends

from ..accounts.deps import current_user
from ..accounts.service import User
from .service import Microproject, check_role, get_by_slug


def get_microproject(microproject_slug: str) -> Microproject:
    """The µprojet of that slug - 404 if there is none."""
    return get_by_slug(microproject_slug)


def require_role(min_role: str):
    """A FastAPI dependency: 403s unless the current user's role in the microproject of the path
    is at least ``min_role`` (``viewer`` < ``editor`` < ``owner``). Returns the resolved
    :class:`Microproject` on success, so a route can depend on this alone.

    The caller is identified first (FastAPI resolves sub-dependencies in parameter order): an
    anonymous request gets its 401 before the microproject is even looked up, rather than a 404
    telling it which slugs exist.
    """

    def dependency(user: User = Depends(current_user), microproject: Microproject = Depends(get_microproject)) -> Microproject:
        check_role(user, microproject, min_role)
        return microproject

    return dependency
