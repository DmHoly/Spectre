"""The strategy layer: management areas (grands thèmes) and the company-wide overview built on
them. Unlike every ``/api/microprojets/{slug}`` router, these routes are not microproject-scoped - every
signed-in user reads them; only an admin (:func:`spectre.core.permissions.require_admin`) writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import management, microprojects
from ..core.accounts import User
from ..core.management import ManagementArea, ManagementAreaNotFoundError
from ..core.permissions import require_admin
from .deps import get_current_user
from .microprojects import _experiment_counts

router = APIRouter(prefix="/api/management", tags=["management"])


class AreaRequest(BaseModel):
    name: str
    description: str = ""
    strategy: str = ""


class AssignRequest(BaseModel):
    microproject_slug: str


def _wafer_count(slug: str) -> int:
    """How many real samples this µprojet tracks: one per non-blank ``physical_tracking`` slot on a
    branch tip (the same "a wafer is a named tracking slot" rule the atlas uses)."""
    total = 0
    for exp in microprojects.branch_tips(microprojects.get_repository(slug)):
        total += sum(1 for e in exp.metadata.get("physical_tracking", []) if e.get("sample_id"))
    return total


def _microproject_stats(slug: str) -> dict:
    running, concluded = _experiment_counts(slug)
    return {"experiences": running + concluded, "running": running, "concluded": concluded, "wafers": _wafer_count(slug)}


def _area_payload(area: ManagementArea, *, with_microprojects: bool = False, user: User | None = None) -> dict:
    area_microprojects = microprojects.list_by_management_area(area.id)
    agg = {"microprojets": len(area_microprojects), "experiences": 0, "running": 0, "concluded": 0, "wafers": 0}
    microproject_rows = []
    for microproject in area_microprojects:
        stats = _microproject_stats(microproject.slug)
        for key in ("experiences", "running", "concluded", "wafers"):
            agg[key] += stats[key]
        if with_microprojects:
            role = microprojects.role_for(microproject.id, user.id) if user else None
            microproject_rows.append(
                {"slug": microproject.slug, "name": microproject.name, "description": microproject.description, "role": role, **stats}
            )
    payload = {
        "id": area.id,
        "slug": area.slug,
        "name": area.name,
        "description": area.description,
        "strategy": area.strategy,
        "stats": agg,
    }
    if with_microprojects:
        payload["microprojets"] = microproject_rows
    return payload


@router.get("")
def list_areas(user: User = Depends(get_current_user)) -> dict:
    """Every area with its rolled-up counts - the payload the company-wide dashboard and the
    management-area leaderboard are both built from."""
    areas = [_area_payload(area) for area in management.list_all()]
    totals = {"themes": len(areas), "microprojets": 0, "experiences": 0, "running": 0, "concluded": 0, "wafers": 0}
    for area in areas:
        totals["microprojets"] += area["stats"]["microprojets"]
        for key in ("experiences", "running", "concluded", "wafers"):
            totals[key] += area["stats"][key]
    conclusion_rate = round(100 * totals["concluded"] / totals["experiences"]) if totals["experiences"] else 0
    return {"areas": areas, "totals": {**totals, "conclusion_rate": conclusion_rate}, "is_admin": user.is_admin}


@router.get("/{slug}")
def get_area(slug: str, user: User = Depends(get_current_user)) -> dict:
    try:
        area = management.get_by_slug(slug)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"thème {slug!r} introuvable") from exc
    return {**_area_payload(area, with_microprojects=True, user=user), "is_admin": user.is_admin}


@router.post("", status_code=201)
def create_area(body: AreaRequest, user: User = Depends(require_admin)) -> dict:
    try:
        area = management.create(body.name, body.description, body.strategy, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _area_payload(area, with_microprojects=True, user=user)


@router.put("/{slug}")
def update_area(slug: str, body: AreaRequest, user: User = Depends(require_admin)) -> dict:
    try:
        area = management.get_by_slug(slug)
        area = management.update(area.id, name=body.name, description=body.description, strategy=body.strategy)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"thème {slug!r} introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _area_payload(area, with_microprojects=True, user=user)


@router.delete("/{slug}")
def delete_area(slug: str, user: User = Depends(require_admin)) -> dict:
    try:
        area = management.get_by_slug(slug)
        management.delete(area.id)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"thème {slug!r} introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": slug}


@router.post("/{slug}/microprojets", status_code=200)
def assign_microproject(slug: str, body: AssignRequest, user: User = Depends(require_admin)) -> dict:
    try:
        area = management.get_by_slug(slug)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"thème {slug!r} introuvable") from exc
    try:
        microproject = microprojects.get_by_slug(body.microproject_slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"µprojet {body.microproject_slug!r} introuvable") from exc
    microprojects.set_management_area(microproject.id, area.id)
    return _area_payload(area, with_microprojects=True, user=user)
