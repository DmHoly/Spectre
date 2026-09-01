"""Who can do what in a project: ``viewer`` reads, ``editor`` also creates/evolves/concludes
experiments and manages step presets, ``owner`` also manages membership. Follow and StructureForge have
no notion of any of this - it lives entirely here, as a FastAPI dependency that resolves the
project from the URL and checks the caller's membership before the route body ever runs.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..api.deps import get_current_user
from .accounts import User
from .projects import ROLE_ORDER, Project, ProjectNotFoundError, get_by_slug, role_for


def get_project(slug: str) -> Project:
    try:
        return get_by_slug(slug)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def require_role(min_role: str):
    """A FastAPI dependency: 403s unless the current user's role in this project is at least
    ``min_role`` (``viewer`` < ``editor`` < ``owner``). Returns the resolved :class:`Project` on
    success, so a route can depend on this alone instead of also depending on :func:`get_project`.
    """

    def dependency(project: Project = Depends(get_project), user: User = Depends(get_current_user)) -> Project:
        role = role_for(project.id, user.id)
        if role is None or ROLE_ORDER[role] < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
        return project

    return dependency
