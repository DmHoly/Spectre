"""``/api/microprojects/{microproject_slug}/step-comments`` : le commentaire de chaque étape d'un procédé
(:mod:`.service`). ``GET`` lit ceux du µprojet - ``?step_id=`` (répétable) pour ne lire que ceux de
quelques étapes ; ``PUT .../{step_id}`` écrit celui d'une étape (texte vide : il est retiré, la réponse
est alors ``{"step_id": ..., "text": ""}``). Lire demande le rôle ``viewer`` du µprojet, écrire ``editor``."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["step_report"])


class CommentInput(BaseModel):
    text: str


@router.get("/step-comments")
def list_step_comments(
    step_id: Annotated[list[str] | None, Query()] = None,
    microproject: Microproject = Depends(require_role("viewer")),
) -> dict:
    return {"comments": {c.step_id: asdict(c) for c in service.list_comments(microproject, step_id)}}


@router.put("/step-comments/{step_id}")
def put_step_comment(
    step_id: str,
    body: CommentInput,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    comment = service.set_comment(microproject, user, step_id, body.text)
    return asdict(comment) if comment else {"step_id": step_id, "text": ""}
