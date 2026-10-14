"""Les plaques jumelles d'une structure (``/api/wafer-twins``). Rien n'est enregistré : la recherche
se refait à chaque appel, sur les études du moment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api", tags=["twins"])


@router.get("/wafer-twins")
def find_twins(
    item: str = Query(min_length=1, max_length=300),
    max_variations: int = Query(0, ge=0, le=service.MAX_VARIATIONS),
    user: User = Depends(current_user),
) -> dict:
    """Les plaques suivies de vos µprojets dont la structure est celle de ``item`` (un jeton du
    comparateur : ``wafer:…``, ``study:…``, ``reference:…``) à ``max_variations`` variations près,
    les plus proches d'abord : ``{base, max_variations, scanned, skipped, truncated, twins}`` (voir
    :func:`service.find`). Un jeton mal formé : 422 ``invalid_comparison_item`` ; une structure sans
    rien à comparer paramètre par paramètre : 422 ``nothing_to_compare``."""
    return service.find(user, item, max_variations)
