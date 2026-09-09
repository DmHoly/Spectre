"""Cross-microproject links: the JSON API for :mod:`spectre.core.links` - create/list/delete a link
between two microprojects, or between two physical entities tracked on (possibly different) microprojects'
experiences. Deliberately top-level like :mod:`spectre.api.atlas` rather than nested under
``/api/microprojets/{slug}`` - a link names two sides, neither one more "the" microproject than the other,
and the atlas (the one screen that shows these) already looks across every microproject at once.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import links, microprojects
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["links"])


def _require_editor_by_slug(slug: str, user: User) -> microprojects.Microproject:
    try:
        microproject = microprojects.get_by_slug(slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"projet {slug!r} introuvable") from exc
    _check_editor(microproject, user)
    return microproject


def _check_editor(microproject: microprojects.Microproject, user: User) -> None:
    role = microprojects.role_for(microproject.id, user.id)
    if role is None or microprojects.ROLE_ORDER[role] < microprojects.ROLE_ORDER["editor"]:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")


class MicroprojectLinkRequest(BaseModel):
    microproject_a: str
    microproject_b: str
    note: str = ""


class EntityRefInput(BaseModel):
    microproject_slug: str
    experience_id: str
    entity_index: int


class EntityLinkRequest(BaseModel):
    a: EntityRefInput
    b: EntityRefInput
    note: str = ""


def _microproject_link_payload(link: links.MicroprojectLink) -> dict:
    return {"id": link.id, "microproject_a_id": link.microproject_a_id, "microproject_b_id": link.microproject_b_id, "note": link.note, "created_at": link.created_at}


def _entity_link_payload(link: links.EntityLink) -> dict:
    return {
        "id": link.id,
        "a": {"microproject_slug": link.a.microproject_slug, "experience_id": link.a.experience_id, "entity_index": link.a.entity_index},
        "b": {"microproject_slug": link.b.microproject_slug, "experience_id": link.b.experience_id, "entity_index": link.b.entity_index},
        "note": link.note,
        "created_at": link.created_at,
    }


@router.post("/liens-projets", status_code=201)
def create_microproject_link(body: MicroprojectLinkRequest, user: User = Depends(get_current_user)) -> dict:
    # Editor on both sides, deliberately: creating a link is asserting something about two
    # microprojects at once, not just your own - see docs-architecture.html for the reasoning.
    microproject_a = _require_editor_by_slug(body.microproject_a, user)
    microproject_b = _require_editor_by_slug(body.microproject_b, user)
    try:
        link = links.create_microproject_link(microproject_a.id, microproject_b.id, note=body.note, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _microproject_link_payload(link)


@router.delete("/liens-projets/{link_id}")
def delete_microproject_link(link_id: int, user: User = Depends(get_current_user)) -> dict:
    link = links.get_microproject_link(link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="lien introuvable")
    # Editor on either side is enough to retract a link - unlike creating one, this doesn't assert
    # anything new about the other microproject, and requiring both would strand a link if the user
    # only ever had access to one side (e.g. removed as a member of the other microproject since).
    # microproject_a_id/microproject_b_id are FK ON DELETE CASCADE (db.py), so both microprojects existing here
    # is guaranteed - get_microproject_link would already have returned None otherwise.
    microproject_a = microprojects.get_by_id(link.microproject_a_id)
    microproject_b = microprojects.get_by_id(link.microproject_b_id)
    role_a = microprojects.role_for(microproject_a.id, user.id)
    role_b = microprojects.role_for(microproject_b.id, user.id)
    can_delete = (role_a is not None and microprojects.ROLE_ORDER[role_a] >= microprojects.ROLE_ORDER["editor"]) or (
        role_b is not None and microprojects.ROLE_ORDER[role_b] >= microprojects.ROLE_ORDER["editor"]
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
    links.delete_microproject_link(link_id)
    return {"status": "ok"}


@router.post("/liens-entites", status_code=201)
def create_entity_link(body: EntityLinkRequest, user: User = Depends(get_current_user)) -> dict:
    _require_editor_by_slug(body.a.microproject_slug, user)
    _require_editor_by_slug(body.b.microproject_slug, user)
    a = links.EntityRef(body.a.microproject_slug, body.a.experience_id, body.a.entity_index)
    b = links.EntityRef(body.b.microproject_slug, body.b.experience_id, body.b.entity_index)
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
    for slug in (link.a.microproject_slug, link.b.microproject_slug):
        try:
            microproject = microprojects.get_by_slug(slug)
        except microprojects.MicroprojectNotFoundError:
            continue
        role = microprojects.role_for(microproject.id, user.id)
        if role is not None and microprojects.ROLE_ORDER[role] >= microprojects.ROLE_ORDER["editor"]:
            can_delete = True
            break
    if not can_delete:
        raise HTTPException(status_code=403, detail="vous n'avez pas les droits nécessaires pour cette action")
    links.delete_entity_link(link_id)
    return {"status": "ok"}
