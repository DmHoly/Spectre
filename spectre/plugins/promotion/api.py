"""Les routes de la promotion, sous ``/api/promotions`` : l'aperçu (les règles, le numéro que
prendrait la version), la promotion elle-même, le journal ; ``/api/promotion-sources`` : les
µprojets où l'on peut promouvoir. Le domaine est dans :mod:`.service`, les règles dans :mod:`.rules`."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from ...kernel.http import created
from ..accounts.deps import current_user
from ..accounts.service import User
from ..references import service as references
from . import service
from .schemas import PromotionRequest

router = APIRouter(prefix="/api", tags=["promotion"])


@router.post("/promotions/preview")
def preview(body: PromotionRequest, user: User = Depends(current_user)) -> dict:
    """Ce que donnerait la promotion, sans rien écrire : la source (les variantes d'un split), la
    référence proposée, la version dont elle dériverait, son numéro et le verdict de chaque règle
    (``rules`` : ``[{rule, label, level, message, code}]``, ``can_promote``)."""
    return service.preview(user, body)


@router.post("/promotions", status_code=201)
def promote(body: PromotionRequest, response: Response, user: User = Depends(current_user)) -> dict:
    """Promouvoir une structure comme (nouvelle version d'une) référence - 201 + ``Location`` vers
    la version ; refusée avec le statut et le code de la première règle qui bloque (403
    ``forbidden``, 422 ``variant_required`` / ``reference_needs_process``, 409
    ``reference_version_identical`` / ``reference_version_already_published``...)."""
    slug, number = service.promote(user, body)
    created(response, f"/api/references/{quote(slug, safe='')}/versions/{number}")
    return references.get_version(user, slug, number)


@router.get("/promotions")
def journal(
    microproject: str | None = Query(None, max_length=200),
    experiment_id: str | None = Query(None, max_length=200),
    limit: int = Query(30, ge=1, le=200),
    user: User = Depends(current_user),
) -> list[dict]:
    """Les promotions, les plus récentes d'abord (celles d'un µprojet, d'une piste)."""
    return service.journal(user, microproject=microproject, experiment_id=experiment_id, limit=limit)


@router.get("/promotion-sources")
def sources(user: User = Depends(current_user)) -> list[dict]:
    """Les µprojets où l'on peut promouvoir (éditeur) : ``[{slug, name}]``."""
    return service.editable_microprojects(user)
