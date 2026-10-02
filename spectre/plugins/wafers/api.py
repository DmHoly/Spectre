"""Plaques : la recherche par lasermark (barre de recherche de la topbar), la page d'une plaque -
toutes les études qui la suivent, d'un µprojet à l'autre - et les identifiants déjà saisis dans un
µprojet. Tout vient de l'index :mod:`spectre.plugins.wafers.service`, limité aux µprojets dont on
est membre.

Les lots qui contiennent une plaque appartiennent au plugin lots, listé après celui-ci : ils sont
lus dans la fonction qui les ajoute à la réponse.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from ..experiments.repository import branch_tips, get_repository
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service as plates

router = APIRouter(prefix="/api", tags=["plates"])


@router.get("/plaques/recherche")
def search_plates(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> list[dict]:
    return plates.search(q, plates.visible_entries(user.id))


@router.get("/plaques/{lasermark}")
def plate(lasermark: str, user: User = Depends(current_user)) -> dict:
    """Une plaque et tout son parcours - vide (aucune étude) plutôt qu'une 404, la page l'explique -
    plus les lots (spectre.plugins.lots.service) qui la contiennent."""
    from ..lots import service as lots

    history = plates.plate_history(lasermark, plates.visible_entries(user.id))
    history["lots"] = lots.lots_for_lasermarks([lasermark])
    return history


@router.get("/microprojets/{slug}/entites/historique")
def entity_history(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Every distinct sample_id/location already used on this microproject's current lines of study -
    feeds the autocomplete on the physical-entities editor (see
    :func:`spectre.plugins.wafers.service.entity_history_for_microproject`).
    """
    repo = get_repository(microproject.slug)
    tips = branch_tips(repo)
    return plates.entity_history_for_microproject(repo, tips)
