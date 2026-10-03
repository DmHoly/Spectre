"""The atlas of a corporate project over HTTP: ``GET /api/areas/{area_slug}/atlas`` (assembled by
:mod:`spectre.plugins.atlas.service`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as atlas

router = APIRouter(prefix="/api", tags=["atlas"])


@router.get("/areas/{area_slug}/atlas")
def get_atlas(area_slug: str, user: User = Depends(current_user)) -> dict:
    return atlas.atlas(area_slug, user)
