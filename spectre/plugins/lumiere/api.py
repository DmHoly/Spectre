"""Les routes du plugin lumiere :

- ``GET /api/lumiere/templates?context=wafer`` : les modèles de rapport (d'un contexte) ;
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

from ...kernel.errors import Forbidden
from ..accounts.deps import current_user
from ..accounts.service import User
from . import service, templates

router = APIRouter(prefix="/api/lumiere", tags=["lumiere"])


class ReportRequest(BaseModel):
    template: str
    context: dict[str, Any]


@router.get("/templates")
def list_templates(context: str | None = None, user: User = Depends(current_user)) -> dict:
    return {"templates": [t.payload() for t in templates.for_context(context)], "contexts": templates.CONTEXTS}


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
