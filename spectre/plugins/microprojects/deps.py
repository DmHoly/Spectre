"""Who can do what in a microproject: ``viewer`` reads, ``editor`` also creates/evolves/concludes
experiments and manages step presets, ``owner`` also manages membership. Follow and StructureForge have
no notion of any of this - it lives entirely here, as a FastAPI dependency that resolves the
microproject from the URL (``{microproject_slug}``) and checks the caller's membership before the
route body ever runs.
"""

from __future__ import annotations

from fastapi import Depends, Request

from ...kernel.errors import Forbidden
from ..accounts.deps import current_user
from ..accounts.service import User
from .service import ROLE_ORDER, Microproject, get_by_slug, role_for


def get_microproject(microproject_slug: str) -> Microproject:
    """The µprojet of that slug - 404 if there is none."""
    return get_by_slug(microproject_slug)


def _microproject_of_path(request: Request) -> Microproject:
    # Transitoire : les routes de la vague 3 encore sous /api/microprojets/{slug} (evidence,
    # notebook, external_images, wafers) nomment ce paramètre ``slug``.
    params = request.path_params
    return get_microproject(params["microproject_slug"] if "microproject_slug" in params else params["slug"])


def require_role(min_role: str):
    """A FastAPI dependency: 403s unless the current user's role in the microproject of the path
    is at least ``min_role`` (``viewer`` < ``editor`` < ``owner``). Returns the resolved
    :class:`Microproject` on success, so a route can depend on this alone.

    The caller is identified first (FastAPI resolves sub-dependencies in parameter order): an
    anonymous request gets its 401 before the microproject is even looked up, rather than a 404
    telling it which slugs exist.
    """

    def dependency(user: User = Depends(current_user), microproject: Microproject = Depends(_microproject_of_path)) -> Microproject:
        role = role_for(microproject.id, user.id)
        if role is None or ROLE_ORDER[role] < ROLE_ORDER[min_role]:
            raise Forbidden("vous n'avez pas les droits nécessaires pour cette action")
        return microproject

    return dependency
