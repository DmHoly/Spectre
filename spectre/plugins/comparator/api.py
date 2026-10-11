"""Comparaisons de structures (``/api/comparisons``) : le tableau d'une liste de plaques, d'études
et de versions de référence, chacune désignée par son jeton (:mod:`.service`), et ce qu'on peut
ajouter à une comparaison pour une saisie (``/api/comparison-candidates``). Rien n'est enregistré :
une comparaison se relit à chaque fois, son adresse (``/comparateur?item=…``) la partage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api", tags=["comparator"])


@router.get("/comparisons")
def get_comparison(
    item: list[str] = Query(default_factory=list, max_length=service.MAX_ITEMS),
    baseline: int = Query(0, ge=0, le=service.MAX_ROWS),
    user: User = Depends(current_user),
) -> dict:
    """Le tableau des ``item`` (des jetons ``study:…``, ``wafer:…``, ``reference:…``, dans l'ordre
    des lignes) comparés à la ligne ``baseline`` : ``{baseline, rows, groups, summary}`` (voir
    :func:`table.build`). Un jeton mal formé : 422 ``invalid_comparison_item`` ; une ligne
    introuvable ou interdite garde sa place, avec son ``error``."""
    return service.compare(user, item, baseline)


@router.get("/comparison-candidates")
def list_candidates(
    q: str = Query("", max_length=80),
    source: list[str] = Query(default_factory=list),
    user: User = Depends(current_user),
) -> list[dict]:
    """Ce qu'on peut ajouter à une comparaison pour la saisie ``q`` - plaques, études, versions de
    référence (``source`` : celles-là seulement) : ``[{item, source, label, sublabel}]``."""
    return service.candidates(user, q, source or None)
