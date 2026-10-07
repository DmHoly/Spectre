"""Plaques (``/api/wafers``) : une seule collection - la recherche par lasermark (``q``) ou par FDL
(``fdl``), les plaques déjà notées dans un µprojet (``microproject``, pour l'autocomplétion de la
fiche) - et le passeport d'une plaque, toutes les études qui la suivent, d'un µprojet à l'autre.
Tout vient de l'index :mod:`.service`, vu selon sa règle de visibilité. Les lots qui contiennent
une plaque se lisent chez eux : ``GET /api/lots?wafer=``.

Les plaques d'une FDL (``/api/fdls/{fdl}``) : celles qu'elle contient réellement, lues dans la source
de :mod:`.fdl_source` (la démo, la base locale saisie à la main, PRISM plus tard) - c'est parmi elles
qu'on associe chaque place d'une étude à une vraie plaque.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..accounts.deps import current_user
from ..accounts.service import User
from ..experiments.entities import MAX_TRACKED_ENTITIES
from . import fdl_source, service

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


class FdlWafersRequest(BaseModel):
    lasermarks: list[str] = Field(..., max_length=MAX_TRACKED_ENTITIES)


@router.get("/fdls/{fdl}")
def get_fdl(fdl: str, user: User = Depends(current_user)) -> dict:
    """Ce qu'on sait d'une FDL (son numéro tel qu'écrit, normalisé) : ``{fdl, source, editable,
    known, wafers: [{lasermark, slot}]}`` - ``known`` faux quand la source ne la connaît pas encore
    (``editable`` : ses plaques se saisissent alors à la main, ``PUT .../wafers``)."""
    return fdl_source.read(fdl)


@router.put("/fdls/{fdl}/wafers")
def set_fdl_wafers(fdl: str, body: FdlWafersRequest, user: User = Depends(current_user)) -> dict:
    """Les plaques d'une FDL, saisies à la main (dans l'ordre du lot) - seulement quand la source est
    la base locale (409 ``fdl_source_read_only`` sinon : la base de la ligne fait foi)."""
    return fdl_source.write(fdl, body.lasermarks, author=user.name)
