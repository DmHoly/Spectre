"""The strategy layer: corporate projects (management areas), their thématiques and ranked
objectives, and the company-wide overview built on them. Unlike every ``/api/microprojets/{slug}``
router, these routes are not microproject-scoped - every signed-in user reads them; only an admin
(:func:`spectre.core.permissions.require_admin`) writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core import management, microprojects, trends
from ..core.accounts import User
from ..core.management import ManagementArea, ManagementAreaNotFoundError, ObjectiveNotFoundError, ThematicNotFoundError
from ..core.permissions import require_admin
from .deps import get_current_user
from .microprojects import _experiment_counts

router = APIRouter(prefix="/api/management", tags=["management"])

_STAT_KEYS = ("experiences", "running", "concluded", "wafers")


class AreaRequest(BaseModel):
    name: str
    description: str = ""
    strategy: str = ""
    objectives_period: str | None = None  # left untouched when omitted
    code_prefix: str | None = None  # prefix of its µprojets' numbers (« Nat »); left untouched / derived when omitted


class AssignRequest(BaseModel):
    microproject_slug: str
    thematique_slug: str | None = None  # None = in the project, without thématique


class ThematicRequest(BaseModel):
    name: str
    description: str = ""


class ObjectiveRequest(BaseModel):
    title: str
    detail: str = ""
    target: str = ""
    weight: float | None = None  # bonus figure, 0-100 %; None = not set
    achieved: bool = False
    validated_by: str | None = None  # slug of the µprojet that validated it


class ReorderRequest(BaseModel):
    ids: list[int]  # most important first


def _get_area(slug: str) -> ManagementArea:
    try:
        return management.get_by_slug(slug)
    except ManagementAreaNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc


def _get_thematic(area: ManagementArea, slug: str) -> management.Thematic:
    try:
        return management.get_thematic(area.id, slug)
    except ThematicNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"thématique {slug!r} introuvable") from exc


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


def _microproject_ref(microproject_id: int | None) -> dict | None:
    if microproject_id is None:
        return None
    try:
        microproject = microprojects.get_by_id(microproject_id)
    except microprojects.MicroprojectNotFoundError:
        return None
    return {"slug": microproject.slug, "code": microproject.code, "name": microproject.name}


def _objective_payload(objective: management.Objective) -> dict:
    return {
        "id": objective.id,
        "title": objective.title,
        "detail": objective.detail,
        "target": objective.target,
        "weight": objective.weight,
        "achieved": objective.achieved,
        "validated_by": _microproject_ref(objective.validated_by),
        "position": objective.position,
    }


def _validated_by_id(slug: str | None) -> int | None:
    if not slug:
        return None
    try:
        return microprojects.get_by_slug(slug).id
    except microprojects.MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=422, detail=f"µprojet {slug!r} introuvable") from exc


def _area_payload(area: ManagementArea, *, detailed: bool = False, user: User | None = None) -> dict:
    """Rolled-up counts for the area; with ``detailed``, also its objectives, its thématiques (each
    with its own counts) and every µprojet row - what the corporate-project page renders."""
    area_microprojects = microprojects.list_by_management_area(area.id)
    thematics = management.list_thematics(area.id)
    agg = {"microprojets": len(area_microprojects), "thematiques": len(thematics), **{k: 0 for k in _STAT_KEYS}}
    per_thematic = {t.id: {"microprojets": 0, **{k: 0 for k in _STAT_KEYS}} for t in thematics}
    slug_by_thematic = {t.id: t.slug for t in thematics}
    microproject_rows = []
    for microproject in area_microprojects:
        stats = _microproject_stats(microproject.slug)
        for key in _STAT_KEYS:
            agg[key] += stats[key]
        bucket = per_thematic.get(microproject.thematic_id)
        if bucket is not None:
            bucket["microprojets"] += 1
            for key in _STAT_KEYS:
                bucket[key] += stats[key]
        if detailed:
            role = microprojects.role_for(microproject.id, user.id) if user else None
            microproject_rows.append(
                {
                    "slug": microproject.slug,
                    "code": microproject.code,
                    "name": microproject.name,
                    "description": microproject.description,
                    "role": role,
                    "thematique_slug": slug_by_thematic.get(microproject.thematic_id),
                    **stats,
                }
            )
    payload = {
        "id": area.id,
        "slug": area.slug,
        "name": area.name,
        "description": area.description,
        "strategy": area.strategy,
        "objectives_period": area.objectives_period,
        "code_prefix": area.code_prefix,
        "stats": agg,
    }
    if detailed:
        payload["objectifs"] = [_objective_payload(o) for o in management.list_objectives(area.id)]
        payload["thematiques"] = [
            {"slug": t.slug, "name": t.name, "description": t.description, "stats": per_thematic[t.id]} for t in thematics
        ]
        payload["microprojets"] = microproject_rows
        if user is not None:
            payload["is_admin"] = user.is_admin
    return payload


def _detailed(area: ManagementArea, user: User) -> dict:
    return _area_payload(management.get_by_id(area.id), detailed=True, user=user)


@router.get("")
def list_areas(user: User = Depends(get_current_user)) -> dict:
    """Every area with its rolled-up counts - the payload the company-wide dashboard and the
    project leaderboard are both built from."""
    areas = [_area_payload(area) for area in management.list_all()]
    totals = {"themes": len(areas), "microprojets": 0, "thematiques": 0, **{k: 0 for k in _STAT_KEYS}}
    for area in areas:
        for key in ("microprojets", "thematiques", *_STAT_KEYS):
            totals[key] += area["stats"][key]
    conclusion_rate = round(100 * totals["concluded"] / totals["experiences"]) if totals["experiences"] else 0
    return {"areas": areas, "totals": {**totals, "conclusion_rate": conclusion_rate}, "is_admin": user.is_admin}


@router.get("/{slug}")
def get_area(slug: str, user: User = Depends(get_current_user)) -> dict:
    return _area_payload(_get_area(slug), detailed=True, user=user)


@router.post("", status_code=201)
def create_area(body: AreaRequest, user: User = Depends(require_admin)) -> dict:
    try:
        area = management.create(body.name, body.description, body.strategy, created_by=user.id, code_prefix=body.code_prefix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _area_payload(area, detailed=True, user=user)


@router.put("/{slug}")
def update_area(slug: str, body: AreaRequest, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        area = management.update(
            area.id,
            name=body.name,
            description=body.description,
            strategy=body.strategy,
            objectives_period=body.objectives_period,
            code_prefix=body.code_prefix,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _area_payload(area, detailed=True, user=user)


@router.delete("/{slug}")
def delete_area(slug: str, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        management.delete(area.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": slug}


@router.post("/{slug}/microprojets", status_code=200)
def assign_microproject(slug: str, body: AssignRequest, user: User = Depends(require_admin)) -> dict:
    """Move a µprojet into this project, and into one of its thématiques (or none)."""
    area = _get_area(slug)
    thematic_id = _get_thematic(area, body.thematique_slug).id if body.thematique_slug else None
    try:
        microproject = microprojects.get_by_slug(body.microproject_slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"µprojet {body.microproject_slug!r} introuvable") from exc
    microprojects.set_management_area(microproject.id, area.id, thematic_id)
    return _detailed(area, user)


# --- thématiques ------------------------------------------------------------------------------


@router.post("/{slug}/thematiques", status_code=201)
def create_thematic(slug: str, body: ThematicRequest, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        management.create_thematic(area.id, body.name, body.description, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detailed(area, user)


@router.put("/{slug}/thematiques/{thematique_slug}")
def update_thematic(slug: str, thematique_slug: str, body: ThematicRequest, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    thematic = _get_thematic(area, thematique_slug)
    try:
        management.update_thematic(thematic.id, name=body.name, description=body.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detailed(area, user)


@router.delete("/{slug}/thematiques/{thematique_slug}")
def delete_thematic(slug: str, thematique_slug: str, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    management.delete_thematic(_get_thematic(area, thematique_slug).id)
    return _detailed(area, user)


# --- objectifs corporate ----------------------------------------------------------------------


@router.post("/{slug}/objectifs", status_code=201)
def create_objective(slug: str, body: ObjectiveRequest, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        management.create_objective(
            area.id,
            body.title,
            body.detail,
            body.target,
            weight=body.weight,
            achieved=body.achieved,
            validated_by=_validated_by_id(body.validated_by),
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detailed(area, user)


@router.put("/{slug}/objectifs")
def reorder_objectives(slug: str, body: ReorderRequest, user: User = Depends(require_admin)) -> dict:
    """New ranking of the whole list, most important first."""
    area = _get_area(slug)
    try:
        management.reorder_objectives(area.id, body.ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detailed(area, user)


@router.put("/{slug}/objectifs/{objective_id}")
def update_objective(slug: str, objective_id: int, body: ObjectiveRequest, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        management.update_objective(
            area.id,
            objective_id,
            title=body.title,
            detail=body.detail,
            target=body.target,
            weight=body.weight,
            achieved=body.achieved,
            validated_by=_validated_by_id(body.validated_by),
        )
    except ObjectiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail="objectif introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detailed(area, user)


@router.delete("/{slug}/objectifs/{objective_id}")
def delete_objective(slug: str, objective_id: int, user: User = Depends(require_admin)) -> dict:
    area = _get_area(slug)
    try:
        management.delete_objective(area.id, objective_id)
    except ObjectiveNotFoundError as exc:
        raise HTTPException(status_code=404, detail="objectif introuvable") from exc
    return _detailed(area, user)


# --- tendances (KPI mensuels, voir spectre.core.trends) ---------------------------------------


def _kpi_payload(kpi: trends.KpiDefinition) -> dict:
    return {
        "key": kpi.key,
        "label": kpi.label,
        "unit": kpi.unit,
        "description": kpi.description,
        "better": kpi.better,
        "source": kpi.source,
        "hook": kpi.hook,
        "status": kpi.status,
        "variants": [{"key": v.key, "label": v.label, "unit": v.unit} for v in kpi.variants],
    }


def _point_payload(point: trends.TrendPoint) -> dict:
    payload = {"period": point.period, "value": point.value}
    if point.study:
        payload["study"] = point.study
        payload["label"] = point.label
    return payload


@router.get("/{slug}/tendances")
def list_trends(slug: str, user: User = Depends(get_current_user)) -> dict:
    """The KPI tabs available for this project - cheap (no data); each tab then loads its own
    series lazily, so a slow PRISM-backed KPI never delays the page."""
    _get_area(slug)
    return {"kpis": [_kpi_payload(k) for k in trends.list_kpis()]}


def _get_kpi(kpi_key: str) -> trends.KpiDefinition:
    try:
        return trends.get_kpi(kpi_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"KPI {kpi_key!r} inconnu") from exc


@router.get("/{slug}/tendances/{kpi_key}")
def get_trend(
    slug: str,
    kpi_key: str,
    mois: int = Query(12, ge=1, le=60),
    variante: str | None = Query(None),
    user: User = Depends(get_current_user),
) -> dict:
    area = _get_area(slug)
    kpi = _get_kpi(kpi_key)
    try:
        variant = kpi.variant(variante)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"variante {variante!r} inconnue pour {kpi_key!r}") from exc
    result = trends.series(kpi_key, area, mois, variant.key if variant else None)
    payload = {
        **_kpi_payload(kpi),
        "status": result.status,
        "message": result.message,
        "target": result.target,
        "periods": trends.month_periods(mois),
        "points": [_point_payload(pt) for pt in result.points],
        "variant": variant.key if variant else None,
    }
    if variant:
        payload["unit"] = variant.unit or kpi.unit
        payload["description"] = variant.description or kpi.description
        payload["variant_label"] = variant.label
    return payload


@router.get("/{slug}/tendances/{kpi_key}/etudes/{study_id}")
def get_trend_study(slug: str, kpi_key: str, study_id: str, user: User = Depends(get_current_user)) -> dict:
    """The fiche of the study behind a point of a demo trend (see :mod:`spectre.core.demo_trends`)
    - a mock: structure, objective, conclusion and a symbolic view of its experiment tree."""
    area = _get_area(slug)
    kpi = _get_kpi(kpi_key)
    if not kpi.demo:
        raise HTTPException(status_code=404, detail="pas de fiche d'étude pour ce KPI")
    from ..core.demo_trends import demo_study

    try:
        return demo_study(area, study_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"étude {study_id!r} introuvable") from exc
