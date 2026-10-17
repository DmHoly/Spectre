"""Analyses de plaques (``/api/analyses``) : leur liste (``?wafer=`` : celles où paraît une plaque), une
analyse, la créer, la changer (titre, question, conclusion, plaques - la première est la référence), la
supprimer (son auteur ou un administrateur). Voir :mod:`.service`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service

router = APIRouter(prefix="/api/analyses", tags=["meta_analysis"])


class CreateAnalysisRequest(BaseModel):
    title: str = Field(..., max_length=service.MAX_TITLE)
    question: str = Field("", max_length=service.MAX_TEXT)
    wafers: list[str] = Field(..., max_length=service.MAX_WAFERS)  # des lasermarks : la référence d'abord


class UpdateAnalysisRequest(BaseModel):
    title: str | None = Field(None, max_length=service.MAX_TITLE)
    question: str | None = Field(None, max_length=service.MAX_TEXT)
    conclusion: str | None = Field(None, max_length=service.MAX_TEXT)
    wafers: list[str] | None = Field(None, max_length=service.MAX_WAFERS)


@router.get("")
def list_analyses(wafer: str | None = Query(None, max_length=service.MAX_LASERMARK), user: User = Depends(current_user)) -> list[dict]:
    """Les analyses, la plus récemment modifiée d'abord ; ``wafer`` : seulement celles où paraît cette plaque."""
    return service.list_all(wafer)


@router.post("", status_code=201)
def create_analysis(body: CreateAnalysisRequest, response: Response, user: User = Depends(current_user)) -> dict:
    """422 ``missing_title``, ``no_wafers``, ``too_many_wafers``."""
    analysis = service.create(user, body.title, body.wafers, body.question)
    response.headers["Location"] = f"/api/analyses/{analysis['id']}"
    return analysis


@router.get("/{analysis_id}")
def get_analysis(analysis_id: int, user: User = Depends(current_user)) -> dict:
    return service.get(analysis_id)


@router.patch("/{analysis_id}")
def update_analysis(analysis_id: int, body: UpdateAnalysisRequest, user: User = Depends(current_user)) -> dict:
    """Les champs envoyés seulement ; ``wafers`` remplace toutes les plaques (la première devient la référence)."""
    return service.update(user, analysis_id, body.model_dump(exclude_unset=True))


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, user: User = Depends(current_user)) -> Response:
    """403 ``not_analysis_author`` pour un autre que son auteur ou un administrateur."""
    service.delete(user, analysis_id)
    return Response(status_code=204)
