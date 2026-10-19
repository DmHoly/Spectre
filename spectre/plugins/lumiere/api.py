"""Les routes du plugin lumiere :

- ``GET /api/lumiere/templates?context=wafer`` : les modèles de rapport (livrés et enregistrés) d'un contexte,
  avec leurs slides ; ``POST /api/lumiere/templates {name, description?, context?, slides?, copy_of?}`` : un
  nouveau modèle (201) ; ``GET|PUT|DELETE /api/lumiere/templates/{key}`` : un modèle, le modifier (son auteur ou un
  administrateur ; un modèle livré ne se modifie pas : 403 ``builtin_template``), le retirer ;
- ``GET /api/lumiere/blocks?context=wafer`` : le catalogue des blocs qu'une slide peut porter, avec leurs options ;
- ``POST /api/lumiere/preview {context, slides, index, key}`` : l'aperçu d'une slide d'un modèle en cours
  d'édition, rendu sur une plaque - ``{html}`` (du HTML sous /api, comme ``structure_svg`` : c'est un document
  Lumière entier, montré dans un cadre) ;
- ``POST /api/lumiere/reports {template, context: {kind, key}}`` : demande un rapport, 202 et la ligne ``queued``
  (la génération part en tâche de fond) ; 422 ``report_running`` si l'un des vôtres est déjà en cours ;
- ``GET /api/lumiere/reports?context_kind=&context_key=`` : vos rapports (tous pour un administrateur) ;
- ``GET /api/lumiere/reports/{id}`` : un rapport et son état ; ``.../file`` : le HTML, en téléchargement ;
- ``DELETE /api/lumiere/reports/{id}`` : le retire (pas en cours) ;
- ``GET /api/lumiere/storage`` : ce que pèsent les rapports gardés (administrateurs).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ...kernel.errors import Forbidden, InvalidInput
from ..accounts.deps import current_user
from ..accounts.service import User
from . import blocks, service, templates

router = APIRouter(prefix="/api/lumiere", tags=["lumiere"])


class ReportRequest(BaseModel):
    template: str
    context: dict[str, Any]


class TemplateInput(BaseModel):
    name: str | None = None
    description: str | None = None
    context: str | None = None
    slides: list[dict[str, Any]] | None = None
    copy_of: str | None = None


class PreviewRequest(BaseModel):
    context: str
    slides: list[dict[str, Any]]
    index: int
    key: str


@router.get("/templates")
def list_templates(context: str | None = None, user: User = Depends(current_user)) -> dict:
    return {"templates": [t.payload() for t in templates.for_context(context)], "contexts": templates.CONTEXTS}


@router.post("/templates", status_code=201)
def create_template(body: TemplateInput, user: User = Depends(current_user)) -> JSONResponse:
    made = templates.create(user, body.model_dump(exclude_none=True))
    return JSONResponse(status_code=201, content=made.payload(), headers={"Location": f"/api/lumiere/templates/{made.key}"})


@router.get("/templates/{key}")
def get_template(key: str, user: User = Depends(current_user)) -> dict:
    return templates.get(key).payload()


@router.put("/templates/{key}")
def update_template(key: str, body: TemplateInput, user: User = Depends(current_user)) -> dict:
    values = body.model_dump(exclude_none=True)
    if "slides" in values and not values["slides"]:
        raise InvalidInput("Un modèle a au moins une slide.", code="no_slides")
    return templates.update(user, key, values).payload()


@router.delete("/templates/{key}", status_code=204)
def delete_template(key: str, user: User = Depends(current_user)) -> Response:
    templates.delete(user, key)
    return Response(status_code=204)


@router.get("/blocks")
def list_blocks(context: str = "wafer", user: User = Depends(current_user)) -> dict:
    if context not in templates.CONTEXTS:
        raise InvalidInput(f"Contexte inconnu : {context!r}.", code="unknown_context")
    return {"blocks": [b.payload(context) for b in blocks.for_context(context)], "slide_kinds": list(templates.SLIDE_KINDS), "max_grid": templates.MAX_GRID}


@router.post("/preview")
def preview_slide(body: PreviewRequest, user: User = Depends(current_user)) -> dict:
    if body.context not in templates.CONTEXTS:
        raise InvalidInput(f"Contexte inconnu : {body.context!r}.", code="unknown_context")
    key = " ".join(body.key.split())
    if not key:
        raise InvalidInput("Indiquez la plaque de l'aperçu (son lasermark).", code="missing_context_key")
    return {"html": templates.preview(user, body.context, body.slides, body.index, key)}


@router.post("/reports", status_code=202)
def create_report(body: ReportRequest, user: User = Depends(current_user)) -> JSONResponse:
    report = service.request(user, body.template, body.context)
    return JSONResponse(status_code=202, content=report, headers={"Location": f"/api/lumiere/reports/{report['id']}"})


@router.get("/reports")
def list_reports(context_kind: str | None = None, context_key: str | None = None, user: User = Depends(current_user)) -> dict:
    return {"reports": service.list_reports(user, context_kind=context_kind, context_key=context_key)}


@router.get("/reports/{report_id}")
def get_report(report_id: int, user: User = Depends(current_user)) -> dict:
    return service.get(user, report_id)


@router.get("/reports/{report_id}/file")
def get_report_file(report_id: int, user: User = Depends(current_user)) -> FileResponse:
    path, filename = service.file_path(user, report_id)
    return FileResponse(path, media_type="text/html; charset=utf-8", filename=filename, headers={"Cache-Control": "private, no-store"})


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, user: User = Depends(current_user)) -> Response:
    service.delete(user, report_id)
    return Response(status_code=204)


@router.get("/storage")
def get_storage(user: User = Depends(current_user)) -> dict:
    if not user.is_admin:
        raise Forbidden("Réservé aux administrateurs.")
    return service.storage()
