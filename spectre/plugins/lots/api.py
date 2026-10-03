"""Suivi de lots (``/api/lots``, domaine dans :mod:`.service`) : la liste (vue Gantt, ou résumée pour
un sélecteur ou des badges), la fiche d'un lot et sa saisie déclarative (priorité P10/P20..., début,
fin prévisionnelle, fin déclarée, wafers, thématiques visées).

Ce que la base ne stocke pas (expériences et thématiques d'un lot, retard, durées) est composé par
:mod:`.views`, sans HTTP.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Response

from ...kernel.http import created, etag, if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as lots
from .schemas import LotCreate, LotPatch, LotThematics, LotWafersAdd
from .service import Lot
from .views import Context, lot_payload, summary_payload

router = APIRouter(prefix="/api", tags=["lots"])


def _respond(response: Response, lot: Lot, user: User) -> dict:
    """Le lot entier, avec sa version en ``ETag`` (à renvoyer en ``If-Match`` pour le modifier)."""
    response.headers["ETag"] = etag(lot.updated_at)
    return lot_payload(lot, Context(user, [lot]))


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/lots")
def list_lots(
    status: str = "",
    q: str = Query("", max_length=80),
    wafer: str = "",
    code: str | None = None,
    view: Literal["full", "summary"] = "full",
    user: User = Depends(current_user),
) -> list[dict]:
    """Les lots par priorité (P10 d'abord) - ou, avec ``q``, par pertinence (code, intitulé, wafer).
    ``status`` : des statuts séparés par des virgules (tous par défaut) ; ``wafer`` : des clés de
    wafer séparées par des virgules (les lots qui contiennent l'une d'elles) ; ``code`` : le code
    exact (sans la casse) ; ``view=summary`` : sans expériences ni thématiques."""
    statuses = lots.check_statuses(_csv(status)) or None
    filters: dict[str, Any] = {"statuses": statuses, "code": code}
    if wafer:
        filters["wafer_keys"] = _csv(wafer)
    if q.strip():
        selected = [lot for lot, _wafer in lots.search(q, statuses=statuses)]
        if wafer or code is not None:
            kept = {lot.id for lot in lots.list_lots(**filters)}
            selected = [lot for lot in selected if lot.id in kept]
    else:
        selected = lots.list_lots(**filters)
    ctx = Context(user, selected)
    payload = summary_payload if view == "summary" else lot_payload
    return [payload(lot, ctx) for lot in selected]


@router.get("/lot-priorities")
def list_priorities(user: User = Depends(current_user)) -> list[str]:
    """Les priorités proposées à la saisie (toute valeur courte est acceptée)."""
    return list(lots.PRIORITIES)


@router.post("/lots", status_code=201)
def create_lot(body: LotCreate, response: Response, user: User = Depends(current_user)) -> dict:
    lot = lots.create(**body.model_dump(), created_by=user.id)
    created(response, f"/api/lots/{lot.id}")
    return _respond(response, lot, user)


@router.get("/lots/{lot_id}")
def get_lot(lot_id: int, response: Response, user: User = Depends(current_user)) -> dict:
    return _respond(response, lots.get(lot_id), user)


@router.patch("/lots/{lot_id}")
def update_lot(lot_id: int, body: LotPatch, response: Response, if_match: str | None = Header(None), user: User = Depends(current_user)) -> dict:
    """Les champs envoyés seulement ; ``If-Match`` : la version affichée (``updated_at``), sinon 412."""
    lot = lots.update(lot_id, body.model_dump(exclude_unset=True), expected_version=if_match_version(if_match))
    return _respond(response, lot, user)


@router.delete("/lots/{lot_id}", status_code=204)
def delete_lot(lot_id: int, user: User = Depends(current_user)) -> Response:
    lots.delete(lot_id, user_id=user.id, is_admin=user.is_admin)
    return Response(status_code=204)


@router.post("/lots/{lot_id}/wafers", status_code=201)
def add_wafers(lot_id: int, body: LotWafersAdd, response: Response, user: User = Depends(current_user)) -> dict:
    """Ajoute des wafers au lot : 201 et le lot ; 200 si tous y étaient déjà (rien n'est écrit).
    Sans ``Location`` : un wafer d'un lot n'a pas de route propre, il se lit dans le lot."""
    if not lots.add_wafers(lot_id, body.lasermarks):
        response.status_code = 200
    return _respond(response, lots.get(lot_id), user)


@router.delete("/lots/{lot_id}/wafers/{wafer_key}", status_code=204)
def remove_wafer(lot_id: int, wafer_key: str, user: User = Depends(current_user)) -> Response:
    lots.remove_wafer(lot_id, wafer_key)
    return Response(status_code=204)


@router.put("/lots/{lot_id}/thematics")
def set_thematics(lot_id: int, body: LotThematics, response: Response, user: User = Depends(current_user)) -> dict:
    """Les thématiques déclarées « visées » (ids de ``GET /api/thematics``), remplacées en bloc."""
    lots.set_thematics(lot_id, body.thematic_ids)
    return _respond(response, lots.get(lot_id), user)
