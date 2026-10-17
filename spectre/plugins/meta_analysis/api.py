"""Analyses de plaques (``/api/analyses``) : leur liste (``?wafer=`` : celles où paraît une plaque), une
analyse, la créer, la changer (titre, question, conclusion, plaques - la première est la référence -, KPI
comparés), la supprimer (son auteur ou un administrateur). Voir :mod:`.service`. Ses données face à la
référence (``/kpis``) et ce qu'on peut y comparer (``/kpi-choices``) : :mod:`.data`."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from ..accounts.deps import current_user
from ..accounts.service import User
from . import data, picker, service

router = APIRouter(prefix="/api/analyses", tags=["meta_analysis"])


class CreateAnalysisRequest(BaseModel):
    title: str = Field(..., max_length=service.MAX_TITLE)
    question: str = Field("", max_length=service.MAX_TEXT)
    wafers: list[str] = Field(..., max_length=service.MAX_WAFERS)  # des lasermarks : la référence d'abord


class KpiInput(BaseModel):
    """Une colonne de KPI d'un type de données PRISM par plaque, ses filtres (vocabulaire des KPI suivis :
    ``{column, op, value}``), un nom libre et le sens d'un écart qui est un progrès."""

    hook: str = Field(..., max_length=120)
    column: str = Field(..., max_length=200)
    label: str = Field("", max_length=200)
    filters: list[dict[str, Any]] = []
    better: Literal["high", "low"] | None = None


class UpdateAnalysisRequest(BaseModel):
    title: str | None = Field(None, max_length=service.MAX_TITLE)
    question: str | None = Field(None, max_length=service.MAX_TEXT)
    conclusion: str | None = Field(None, max_length=service.MAX_TEXT)
    wafers: list[str] | None = Field(None, max_length=service.MAX_WAFERS)
    kpis: list[KpiInput] | None = Field(None, max_length=service.MAX_KPIS)


@router.get("")
def list_analyses(wafer: str | None = Query(None, max_length=service.MAX_LASERMARK), user: User = Depends(current_user)) -> list[dict]:
    """Les analyses, la plus récemment modifiée d'abord ; ``wafer`` : seulement celles où paraît cette plaque."""
    return service.list_all(wafer)


@router.get("/wafer-search")
def search_wafers(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> dict:
    """Les plaques à ajouter à une analyse, cherchées comme dans la barre du haut - lasermark, run d'épitaxie, lot,
    µprojet, FDL : ``{groups: [{kind, label, detail, total, wafers: [{key, lasermark, detail}]}]}`` (voir
    :mod:`.picker`)."""
    return picker.search(user, q)


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
    """Les champs envoyés seulement ; ``wafers`` remplace toutes les plaques (la première devient la référence),
    ``kpis`` tous les KPI comparés (422 ``unknown_kpi``, ``unknown_filter_column``, ``too_many_kpis``...)."""
    return service.update(user, analysis_id, body.model_dump(exclude_unset=True))


@router.get("/{analysis_id}/kpis")
def get_analysis_kpis(analysis_id: int, refresh: bool = False, user: User = Depends(current_user)) -> dict:
    """Pour chaque KPI comparé, une boîte à moustaches par plaque (sa mesure la plus récente) et l'écart de sa
    médiane à la référence : ``{source, kpis: [{..., status, message, groups: [{key, wafer, date, dates, stats,
    outliers, delta: {absolute, relative}}]}]}`` - calculé à la demande ; ``refresh`` retape la base."""
    return data.kpis(service.get(analysis_id), refresh=refresh)


@router.get("/{analysis_id}/kpi-choices")
def get_kpi_choices(analysis_id: int, user: User = Depends(current_user)) -> dict:
    """Ce qu'on peut comparer : ``catalog`` (les colonnes de KPI de PRISM) et ``suggested`` (les KPI que suivent
    les projets corporate de ses plaques, sans ceux déjà comparés)."""
    return data.kpi_choices(user, service.get(analysis_id))


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, user: User = Depends(current_user)) -> Response:
    """403 ``not_analysis_author`` pour un autre que son auteur ou un administrateur."""
    service.delete(user, analysis_id)
    return Response(status_code=204)
