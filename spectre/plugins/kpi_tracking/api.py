"""``/api/microprojects/{microproject_slug}/kpi-tracking`` : les KPI qu'un µprojet suit et leurs
distributions sur ses plaques (:mod:`.service`). Lire demande le rôle ``viewer`` du µprojet, choisir
ses KPI ``editor`` ; ``?refresh=true`` (retaper la base de PRISM) aussi ``editor``."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject, check_role
from . import service

router = APIRouter(prefix="/api/microprojects/{microproject_slug}/kpi-tracking", tags=["kpi_tracking"])


class TrackKpiRequest(BaseModel):
    hook: str
    column: str
    label: str | None = None


class RenameKpiRequest(BaseModel):
    label: str


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


def _catalog_payload() -> dict[str, service.CatalogKpi]:
    return {k.key: k for k in service.catalog()}


@router.get("/catalog")
def get_catalog(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    """Les KPI qu'on peut suivre : une colonne de KPI par type de données PRISM par plaque."""
    return [{**asdict(k), "key": k.key} for k in service.catalog()]


@router.get("/kpis")
def list_tracked_kpis(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    catalogue = _catalog_payload()
    return [_tracked_payload(k, catalogue) for k in service.list_tracked(microproject)]


@router.post("/kpis", status_code=201)
def track_kpi(
    body: TrackKpiRequest,
    response: Response,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    kpi = service.add_tracked(microproject, user, body.hook, body.column, body.label)
    response.headers["Location"] = f"/api/microprojects/{microproject.slug}/kpi-tracking/kpis/{kpi.id}"
    return _tracked_payload(kpi, _catalog_payload())


@router.patch("/kpis/{kpi_id}")
def rename_kpi(kpi_id: int, body: RenameKpiRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    return _tracked_payload(service.rename_tracked(microproject, kpi_id, body.label), _catalog_payload())


@router.delete("/kpis/{kpi_id}", status_code=204)
def untrack_kpi(kpi_id: int, microproject: Microproject = Depends(require_role("editor"))) -> Response:
    service.remove_tracked(microproject, kpi_id)
    return Response(status_code=204)


@router.get("/distributions")
def get_distributions(
    refresh: bool = False,
    microproject: Microproject = Depends(require_role("viewer")),
    user: User = Depends(current_user),
) -> dict:
    """Une boîte à moustaches par plaque suivie et par KPI suivi, calculée à la demande."""
    if refresh:
        check_role(user, microproject, "editor")
    result = service.distributions(microproject, refresh=refresh)
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
                    {"wafer": g.wafer, "studies": g.studies, "stats": asdict(g.stats) if g.stats else None, "outliers": g.outliers}
                    for g in d.groups
                ],
            }
            for d in result.kpis
        ],
    }
