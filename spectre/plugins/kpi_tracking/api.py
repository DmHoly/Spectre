"""``/api/areas/{area_slug}/kpi-tracking`` : les KPI qu'un projet corporate suit et leurs distributions sur
les plaques de tous ses µprojets (:mod:`.service`). Lire est ouvert à tout compte connecté, comme les
tendances du projet (:mod:`spectre.plugins.kpis`) ; choisir ses KPI, et ``?refresh=true`` (retaper la base de
PRISM), demandent de pouvoir gérer le projet (un administrateur, ou un manager d'une de ses équipes)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from . import service

router = APIRouter(prefix="/api/areas/{area_slug}/kpi-tracking", tags=["kpi_tracking"])


class TrackKpiRequest(BaseModel):
    hook: str
    column: str
    label: str | None = None


class RenameKpiRequest(BaseModel):
    label: str


def _managed(area_slug: str, user: User) -> areas.ManagementArea:
    area = areas.get_by_slug(area_slug)
    areas.require_manage(user, area)
    return area


def _tracked_payload(kpi: service.TrackedKpi, catalogue: dict[str, service.CatalogKpi]) -> dict:
    entry = catalogue.get(f"{kpi.hook}:{kpi.column}")
    return {
        "id": kpi.id,
        "hook": kpi.hook,
        "column": kpi.column,
        "label": kpi.label,
        "title": kpi.title,
        "unit": entry.unit if entry else "",
        "description": entry.description if entry else "",
        "hook_title": entry.hook_title if entry else kpi.hook,
        "available": entry is not None,  # False : le KPI a disparu du catalogue PRISM
        "created_at": kpi.created_at,
    }


def _catalogue() -> dict[str, service.CatalogKpi]:
    return {k.key: k for k in service.catalog()}


@router.get("/catalog")
def get_catalog(area_slug: str, user: User = Depends(current_user)) -> list[dict]:
    """Les KPI qu'on peut suivre : une colonne de KPI par type de données PRISM par plaque."""
    areas.get_by_slug(area_slug)
    return [{**asdict(k), "key": k.key} for k in service.catalog()]


@router.get("/kpis")
def list_tracked_kpis(area_slug: str, user: User = Depends(current_user)) -> list[dict]:
    area = areas.get_by_slug(area_slug)
    catalogue = _catalogue()
    return [_tracked_payload(k, catalogue) for k in service.list_tracked(area)]


@router.post("/kpis", status_code=201)
def track_kpi(area_slug: str, body: TrackKpiRequest, response: Response, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    kpi = service.add_tracked(area, user, body.hook, body.column, body.label)
    response.headers["Location"] = f"/api/areas/{area.slug}/kpi-tracking/kpis/{kpi.id}"
    return _tracked_payload(kpi, _catalogue())


@router.patch("/kpis/{kpi_id}")
def rename_kpi(area_slug: str, kpi_id: int, body: RenameKpiRequest, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    return _tracked_payload(service.rename_tracked(area, kpi_id, body.label), _catalogue())


@router.delete("/kpis/{kpi_id}", status_code=204)
def untrack_kpi(area_slug: str, kpi_id: int, user: User = Depends(current_user)) -> Response:
    service.remove_tracked(_managed(area_slug, user), kpi_id)
    return Response(status_code=204)


@router.get("/distributions")
def get_distributions(area_slug: str, refresh: bool = False, user: User = Depends(current_user)) -> dict:
    """Une boîte à moustaches par plaque du projet et par KPI suivi, calculée à la demande."""
    area = _managed(area_slug, user) if refresh else areas.get_by_slug(area_slug)
    result = service.distributions(area, user, refresh=refresh)
    return {
        "source": result.source,
        "wafers": result.wafers,
        "kpis": [
            {
                **_tracked_payload(d.kpi, {}),
                "unit": d.unit,
                "description": d.description,
                "hook_title": d.hook_title or d.kpi.hook,
                "available": d.status != "unavailable",
                "status": d.status,
                "message": d.message,
                "groups": [
                    {
                        "wafer": g.wafer,
                        "microprojects": g.microprojects,
                        "studies": g.studies,
                        "stats": asdict(g.stats) if g.stats else None,
                        "outliers": g.outliers,
                    }
                    for g in d.groups
                ],
            }
            for d in result.kpis
        ],
    }
