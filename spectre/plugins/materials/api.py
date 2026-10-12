"""La bibliothèque de matériaux de l'instance sous forme de document : ``GET /api/material-library`` (tout
compte connecté) et ``PUT /api/material-library`` (un administrateur : ce qu'il change vaut pour tous les
µprojets). Le document : les matériaux du sélecteur et les dégradés de couleur de l'InGaN et de l'AlGaN."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from ..accounts.deps import current_user, require_admin
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api", tags=["materials"])


def _with_rights(document: dict[str, Any], user: User) -> dict[str, Any]:
    return {**document, "can_edit": user.is_admin}


@router.get("/material-library")
def get_material_library(user: User = Depends(current_user)) -> dict[str, Any]:
    return _with_rights(service.read_document(), user)


@router.put("/material-library")
def save_material_library(document: Any = Body(...), user: User = Depends(require_admin)) -> dict[str, Any]:
    return _with_rights(service.save_document(document), user)
