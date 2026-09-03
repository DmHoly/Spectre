"""Cross-project links: the JSON API for :mod:`spectre.core.links` - create/list/delete a link
between two projects, or between two physical entities tracked on (possibly different) projects'
experiences. Deliberately top-level like :mod:`spectre.api.atlas` rather than nested under
``/api/projects/{slug}`` - a link names two sides, neither one more "the" project than the other,
and the atlas (the one screen that shows these) already looks across every project at once.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import links, projects
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["links"])


def _require_editor_by_slug(slug: str, user: User) -> projects.Project:
    try:
        project = projects.get_by_slug(slug)
    except projects.ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc
    _check_editor(project, user)
    return project


def _check_editor(project: projects.Project, user: User) -> None:
    role = projects.role_for(project.id, user.id)
    if role is None or projects.ROLE_ORDER[role] < projects.ROLE_ORDER["editor"]:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")


class ProjectLinkRequest(BaseModel):
    project_a: str
    project_b: str
    note: str = ""


class EntityRefInput(BaseModel):
    project_slug: str
    experience_id: str
    entity_index: int


class EntityLinkRequest(BaseModel):
    a: EntityRefInput
    b: EntityRefInput
    note: str = ""


def _project_link_payload(link: links.ProjectLink) -> dict:
    return {"id": link.id, "project_a_id": link.project_a_id, "project_b_id": link.project_b_id, "note": link.note, "created_at": link.created_at}


def _entity_link_payload(link: links.EntityLink) -> dict:
    return {
        "id": link.id,
        "a": {"project_slug": link.a.project_slug, "experience_id": link.a.experience_id, "entity_index": link.a.entity_index},
        "b": {"project_slug": link.b.project_slug, "experience_id": link.b.experience_id, "entity_index": link.b.entity_index},
        "note": link.note,
        "created_at": link.created_at,
    }


@router.post("/liens-projets", status_code=201)
def create_project_link(body: ProjectLinkRequest, user: User = Depends(get_current_user)) -> dict:
    # Editor on both sides, deliberately: creating a link is asserting something about two
    # projects at once, not just your own - see docs-architecture.html for the reasoning.
    project_a = _require_editor_by_slug(body.project_a, user)
    project_b = _require_editor_by_slug(body.project_b, user)
    try:
        link = links.create_project_link(project_a.id, project_b.id, note=body.note, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _project_link_payload(link)


@router.delete("/liens-projets/{link_id}")
def delete_project_link(link_id: int, user: User = Depends(get_current_user)) -> dict:
    link = links.get_project_link(link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="lien introuvable")
    # Editor on either side is enough to retract a link - unlike creating one, this doesn't assert
    # anything new about the other project, and requiring both would strand a link if the user
    # only ever had access to one side (e.g. removed as a member of the other project since).
    # project_a_id/project_b_id are FK ON DELETE CASCADE (db.py), so both projects existing here
    # is guaranteed - get_project_link would already have returned None otherwise.
    project_a = projects.get_by_id(link.project_a_id)
    project_b = projects.get_by_id(link.project_b_id)
    role_a = projects.role_for(project_a.id, user.id)
    role_b = projects.role_for(project_b.id, user.id)
    can_delete = (role_a is not None and projects.ROLE_ORDER[role_a] >= projects.ROLE_ORDER["editor"]) or (
        role_b is not None and projects.ROLE_ORDER[role_b] >= projects.ROLE_ORDER["editor"]
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
    links.delete_project_link(link_id)
    return {"status": "ok"}


@router.post("/liens-entites", status_code=201)
def create_entity_link(body: EntityLinkRequest, user: User = Depends(get_current_user)) -> dict:
    _require_editor_by_slug(body.a.project_slug, user)
    _require_editor_by_slug(body.b.project_slug, user)
    a = links.EntityRef(body.a.project_slug, body.a.experience_id, body.a.entity_index)
    b = links.EntityRef(body.b.project_slug, body.b.experience_id, body.b.entity_index)
    try:
        link = links.create_entity_link(a, b, note=body.note, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _entity_link_payload(link)


@router.delete("/liens-entites/{link_id}")
def delete_entity_link(link_id: int, user: User = Depends(get_current_user)) -> dict:
    link = links.get_entity_link(link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="lien introuvable")
    can_delete = False
    for slug in (link.a.project_slug, link.b.project_slug):
        try:
            project = projects.get_by_slug(slug)
        except projects.ProjectNotFoundError:
            continue
        role = projects.role_for(project.id, user.id)
        if role is not None and projects.ROLE_ORDER[role] >= projects.ROLE_ORDER["editor"]:
            can_delete = True
            break
    if not can_delete:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
    links.delete_entity_link(link_id)
    return {"status": "ok"}
