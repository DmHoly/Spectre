"""Plaques : la recherche par lasermark (barre de recherche de la topbar) et la page d'une plaque -
toutes les études qui la suivent, d'un µprojet à l'autre. Tout vient de l'index
:mod:`spectre.core.plates`, limité aux µprojets dont on est membre.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..core import plates
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api/plaques", tags=["plates"])


@router.get("/recherche")
def search_plates(q: str = Query("", max_length=80), user: User = Depends(get_current_user)) -> list[dict]:
    return plates.search(q, plates.visible_entries(user.id))


@router.get("/{lasermark}")
def plate(lasermark: str, user: User = Depends(get_current_user)) -> dict:
    """Une plaque et tout son parcours - vide (aucune étude) plutôt qu'une 404, la page l'explique."""
    return plates.plate_history(lasermark, plates.visible_entries(user.id))
