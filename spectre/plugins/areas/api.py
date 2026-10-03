"""The strategy layer over HTTP: corporate projects (``/api/areas``), their thématiques and their
ranked objectives, plus the flat list of every thématique (``/api/thematics``). Every signed-in
user reads them; only an admin (:func:`spectre.plugins.accounts.deps.require_admin`) writes.

What the µprojets of a project are doing (their counts, the thématique's frise) is read from the
experiments plugin (``GET /api/experiment-stats``, ``GET /api/experiment-timeline``), and a µprojet
moves between projects by ``PATCH /api/microprojects/{microproject_slug}``: this plugin, listed
below both, knows nothing of them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..accounts.deps import current_user, require_admin
from ..accounts.service import User
from . import service as areas
from .schemas import AreaCreate, AreaPatch, ObjectiveCreate, ObjectivePatch, ThematicCreate, ThematicPatch
from .service import ManagementArea, Objective, Thematic

router = APIRouter(prefix="/api", tags=["areas"])


def _area_ref(area: ManagementArea) -> dict:
    return {"slug": area.slug, "name": area.name}


def _area_payload(area: ManagementArea) -> dict:
    return {
        "id": area.id,
        "slug": area.slug,
        "name": area.name,
        "description": area.description,
        "strategy": area.strategy,
        "objectives_period": area.objectives_period,
        "horizon_months": area.horizon_months,
        "code_prefix": area.code_prefix,
        "is_system": area.is_system,
        "can_delete": not area.is_system,
    }


def _thematic_payload(thematic: Thematic, area: ManagementArea) -> dict:
    return {
        "id": thematic.id,
        "slug": thematic.slug,
        "name": thematic.name,
        "description": thematic.description,
        "position": thematic.position,
        "area": _area_ref(area),
    }


def _objective_payload(objective: Objective) -> dict:
    return {
        "id": objective.id,
        "title": objective.title,
        "detail": objective.detail,
        "target": objective.target,
        "weight": objective.weight,
        "achieved": objective.achieved,
        "validated_by": objective.validated_by,
        "position": objective.position,
    }


def _area_detail(area: ManagementArea) -> dict:
    """The project page's own data: the project, its thématiques and its objectives."""
    return {
        **_area_payload(area),
        "thematics": [_thematic_payload(t, area) for t in areas.list_thematics(area.id)],
        "objectives": [_objective_payload(o) for o in areas.list_objectives(area.id)],
    }


def _created(response: Response, location: str) -> None:
    response.headers["Location"] = location


def _no_content() -> Response:
    return Response(status_code=204)


# --- projets corporate -------------------------------------------------------------------------


@router.get("/areas")
def list_areas(user: User = Depends(current_user)) -> list[dict]:
    """Every project, the system one (« Non classé ») last."""
    return [_area_payload(area) for area in areas.list_all()]


@router.post("/areas", status_code=201)
def create_area(body: AreaCreate, response: Response, user: User = Depends(require_admin)) -> dict:
    area = areas.create(body.name, body.description, body.strategy, created_by=user.id, code_prefix=body.code_prefix)
    _created(response, f"/api/areas/{area.slug}")
    return _area_detail(area)


@router.get("/areas/{area_slug}")
def get_area(area_slug: str, user: User = Depends(current_user)) -> dict:
    return _area_detail(areas.get_by_slug(area_slug))


@router.patch("/areas/{area_slug}")
def update_area(area_slug: str, body: AreaPatch, user: User = Depends(require_admin)) -> dict:
    area = areas.update(areas.get_by_slug(area_slug), **body.model_dump(exclude_unset=True))
    return _area_detail(area)


@router.delete("/areas/{area_slug}", status_code=204)
def delete_area(area_slug: str, user: User = Depends(require_admin)) -> Response:
    """Its µprojets go back to the system area; the system area itself can't be deleted (409)."""
    areas.delete(areas.get_by_slug(area_slug))
    return _no_content()


# --- thématiques ------------------------------------------------------------------------------


@router.get("/thematics")
def list_thematics(area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    """Every thématique (of one project with ``?area=``), project by project - e.g. to pick those a
    lot aims at."""
    if area:
        project = areas.get_by_slug(area)
        by_id, thematics = {project.id: project}, areas.list_thematics(project.id)
    else:
        by_id, thematics = {project.id: project for project in areas.list_all()}, areas.list_thematics()
    return [{"id": t.id, "slug": t.slug, "name": t.name, "area": _area_ref(by_id[t.management_area_id])} for t in thematics]


@router.post("/areas/{area_slug}/thematics", status_code=201)
def create_thematic(area_slug: str, body: ThematicCreate, response: Response, user: User = Depends(require_admin)) -> dict:
    area = areas.get_by_slug(area_slug)
    thematic = areas.create_thematic(area, body.name, body.description, created_by=user.id)
    _created(response, f"/api/areas/{area.slug}/thematics/{thematic.slug}")
    return _thematic_payload(thematic, area)


@router.get("/areas/{area_slug}/thematics/{thematic_slug}")
def get_thematic(area_slug: str, thematic_slug: str, user: User = Depends(current_user)) -> dict:
    area = areas.get_by_slug(area_slug)
    return _thematic_payload(areas.get_thematic(area.id, thematic_slug), area)


@router.patch("/areas/{area_slug}/thematics/{thematic_slug}")
def update_thematic(area_slug: str, thematic_slug: str, body: ThematicPatch, user: User = Depends(require_admin)) -> dict:
    area = areas.get_by_slug(area_slug)
    thematic = areas.update_thematic(areas.get_thematic(area.id, thematic_slug), **body.model_dump(exclude_unset=True))
    return _thematic_payload(thematic, area)


@router.delete("/areas/{area_slug}/thematics/{thematic_slug}", status_code=204)
def delete_thematic(area_slug: str, thematic_slug: str, user: User = Depends(require_admin)) -> Response:
    """Its µprojets stay in the project, without thématique."""
    area = areas.get_by_slug(area_slug)
    areas.delete_thematic(areas.get_thematic(area.id, thematic_slug))
    return _no_content()


# --- objectifs corporate ----------------------------------------------------------------------


@router.post("/areas/{area_slug}/objectives", status_code=201)
def create_objective(area_slug: str, body: ObjectiveCreate, response: Response, user: User = Depends(require_admin)) -> dict:
    area = areas.get_by_slug(area_slug)
    objective = areas.create_objective(
        area,
        body.title,
        body.detail,
        body.target,
        weight=body.weight,
        achieved=body.achieved,
        validated_by=body.validated_by,
        created_by=user.id,
    )
    _created(response, f"/api/areas/{area.slug}/objectives/{objective.id}")
    return _objective_payload(objective)


@router.patch("/areas/{area_slug}/objectives/{objective_id}")
def update_objective(area_slug: str, objective_id: int, body: ObjectivePatch, user: User = Depends(require_admin)) -> dict:
    area = areas.get_by_slug(area_slug)
    return _objective_payload(areas.update_objective(area, objective_id, **body.model_dump(exclude_unset=True)))


@router.delete("/areas/{area_slug}/objectives/{objective_id}", status_code=204)
def delete_objective(area_slug: str, objective_id: int, user: User = Depends(require_admin)) -> Response:
    areas.delete_objective(areas.get_by_slug(area_slug), objective_id)
    return _no_content()
