"""Plaques (``/api/wafers``) : une seule collection - la recherche par lasermark (``q``) ou par FDL
(``fdl``), les plaques déjà notées dans un µprojet (``microproject``, pour l'autocomplétion de la
fiche) - et le passeport d'une plaque, toutes les études qui la suivent, d'un µprojet à l'autre.
Tout vient de l'index :mod:`.service`, vu selon sa règle de visibilité. Les lots qui contiennent
une plaque se lisent chez eux : ``GET /api/lots?wafer=``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api", tags=["wafers"])


@router.get("/wafers")
def list_wafers(
    q: str = Query("", max_length=80),
    fdl: str = Query("", max_length=80),
    microproject: str | None = None,
    user: User = Depends(current_user),
) -> list[dict]:
    """Les plaques (``key``, ``lasermark``, ``count``, ``microprojects``, ``latest``, ``fdl``,
    ``locations``) dont le lasermark correspond à ``q``, qui portent une FDL correspondant à ``fdl``,
    suivies dans le µprojet ``microproject`` (dont il faut être membre) - les filtres se cumulent."""
    scope = service.microproject_for(user, microproject) if microproject else None
    return service.wafers(service.occurrences(user, microproject=scope), q=q, fdl=fdl)


@router.get("/wafers/{wafer_key}")
def get_wafer(wafer_key: str, user: User = Depends(current_user)) -> dict:
    """Le passeport d'une plaque (``wafer_key``, ou son lasermark tel qu'écrit : il est comparé
    sans casse ni séparateurs) - vide (aucune étude) plutôt qu'une 404, la page l'explique."""
    return service.passport(wafer_key, service.occurrences(user, keys=[wafer_key]))
