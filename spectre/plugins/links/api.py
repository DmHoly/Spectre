"""Cross-microproject links over HTTP (:mod:`spectre.plugins.links.service`): ``/api/microproject-links``
and ``/api/entity-links``. Top-level rather than nested under a microproject - a link names two sides,
neither one more "the" microproject than the other. Each collection reads ``?microproject=`` and
``?area=`` (slugs): the links touching that microproject, or a microproject of that corporate project.

A link has no route of its own to read it back (it is read in its collection): a creation answers
201 and the link, without ``Location``.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as links
from .schemas import EntityLinkCreate, EntityRefInput, MicroprojectLinkCreate

router = APIRouter(prefix="/api", tags=["links"])


def _entity(ref: EntityRefInput) -> links.EntityRef:
    return links.EntityRef(ref.microproject, ref.experiment_id, ref.entity_index)


@router.get("/microproject-links")
def list_microproject_links(microproject: str | None = None, area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    return [asdict(link) for link in links.list_microproject_links(user, microproject=microproject, area=area)]


@router.post("/microproject-links", status_code=201)
def create_microproject_link(body: MicroprojectLinkCreate, user: User = Depends(current_user)) -> dict:
    return asdict(links.create_microproject_link(user, body.a, body.b, note=body.note))


@router.delete("/microproject-links/{link_id}", status_code=204)
def delete_microproject_link(link_id: int, user: User = Depends(current_user)) -> Response:
    links.delete_microproject_link(user, link_id)
    return Response(status_code=204)


@router.get("/entity-links")
def list_entity_links(microproject: str | None = None, area: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    return [asdict(link) for link in links.list_entity_links(user, microproject=microproject, area=area)]


@router.post("/entity-links", status_code=201)
def create_entity_link(body: EntityLinkCreate, user: User = Depends(current_user)) -> dict:
    return asdict(links.create_entity_link(user, _entity(body.a), _entity(body.b), note=body.note))


@router.delete("/entity-links/{link_id}", status_code=204)
def delete_entity_link(link_id: int, user: User = Depends(current_user)) -> Response:
    links.delete_entity_link(user, link_id)
    return Response(status_code=204)
