"""``GET /api/search?q=&types=`` : la recherche de la barre du haut (:mod:`.service`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(q: str = Query("", max_length=80), types: str = "", user: User = Depends(current_user)) -> list[dict]:
    """``types`` : des types de résultat séparés par des virgules (``wafer,fdl``) ; tous par défaut."""
    wanted = [value.strip() for value in types.split(",") if value.strip()]
    return service.search(q, user, wanted or None)
