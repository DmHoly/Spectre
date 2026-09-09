"""Microprojects and membership: the only "who can see/do what" concept in Spectre. Every other
router (structures, experiments) sits behind :func:`spectre.core.permissions.require_role` for a
microproject resolved here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import atlas as atlas_core
from ..core import management, microprojects
from ..core.accounts import User
from ..core.management import ManagementAreaNotFoundError
from ..core.permissions import require_admin, require_role
from ..core.microprojects import Microproject
from .deps import get_current_user

router = APIRouter(prefix="/api/microprojets", tags=["microprojects"])

RUNNING_STATUSES = microprojects.RUNNING_STATUSES
CONCLUDED_STATUSES = microprojects.CONCLUDED_STATUSES


class CreateMicroprojectRequest(BaseModel):
    name: str
    description: str = ""
    management_area_slug: str | None = None  # which grand thème it belongs to (default: « Non classé »)


class AddMemberRequest(BaseModel):
    email: str
    role: str


def _experiment_counts(slug: str) -> tuple[int, int]:
    tips = microprojects.branch_tips(microprojects.get_repository(slug))
    running = sum(1 for exp in tips if exp.conclusion.status in RUNNING_STATUSES)
    concluded = sum(1 for exp in tips if exp.conclusion.status in CONCLUDED_STATUSES)
    return running, concluded


def _area_ref(management_area_id: int | None) -> dict | None:
    if management_area_id is None:
        return None
    try:
        area = management.get_by_id(management_area_id)
    except ManagementAreaNotFoundError:
        return None
    return {"slug": area.slug, "name": area.name}


def _microproject_payload(microproject: Microproject, role: str) -> dict:
    running, concluded = _experiment_counts(microproject.slug)
    return {
        "id": microproject.id,
        "slug": microproject.slug,
        "name": microproject.name,
        "description": microproject.description,
        "role": role,
        "running_count": running,
        "concluded_count": concluded,
        "management_area": _area_ref(microproject.management_area_id),
    }


@router.get("")
def list_microprojects(user: User = Depends(get_current_user)) -> list[dict]:
    return [_microproject_payload(microproject, role) for microproject, role in microprojects.list_for_user(user.id)]


@router.post("", status_code=201)
def create_microproject(body: CreateMicroprojectRequest, user: User = Depends(get_current_user)) -> dict:
    area_id = None
    if body.management_area_slug:
        try:
            area_id = management.get_by_slug(body.management_area_slug).id
        except ManagementAreaNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"thème {body.management_area_slug!r} introuvable") from exc
    try:
        microproject = microprojects.create(body.name, body.description, owner_id=user.id, management_area_id=area_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _microproject_payload(microproject, "owner")


@router.get("/tous")
def list_all_microprojects(_admin: User = Depends(require_admin)) -> list[dict]:
    """Every µprojet, whichever theme it sits in - admin only, for the "move a µprojet into this
    theme" picker on the management-area page."""
    return [
        {"slug": p.slug, "name": p.name, "management_area": _area_ref(p.management_area_id)}
        for p in microprojects.list_all()
    ]


@router.get("/{slug}")
def get_microproject(microproject: Microproject = Depends(require_role("viewer")), user: User = Depends(get_current_user)) -> dict:
    role = microprojects.role_for(microproject.id, user.id)
    return _microproject_payload(microproject, role)


@router.get("/{slug}/members")
def list_members(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return microprojects.list_members(microproject.id)


@router.post("/{slug}/members", status_code=201)
def add_member(
    body: AddMemberRequest, microproject: Microproject = Depends(require_role("owner")), user: User = Depends(get_current_user)
) -> dict:
    try:
        status = microprojects.add_member(microproject.id, microproject.name, body.email, body.role, invited_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": status, "members": microprojects.list_members(microproject.id), "invitations": microprojects.list_invitations(microproject.id)}


@router.get("/{slug}/invitations")
def list_invitations(microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    return microprojects.list_invitations(microproject.id)


@router.delete("/{slug}/invitations/{token}")
def cancel_invitation(token: str, microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    microprojects.cancel_invitation(microproject.id, token)
    return microprojects.list_invitations(microproject.id)


@router.delete("/{slug}/members/{user_id}")
def remove_member(user_id: int, microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    if user_id == microproject.created_by:
        raise HTTPException(status_code=400, detail="impossible de retirer la personne qui a créé le projet")
    microprojects.remove_member(microproject.id, user_id)
    return microprojects.list_members(microproject.id)


@router.get("/{slug}/entites/historique")
def entity_history(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Every distinct sample_id/location already used on this microproject's current lines of study -
    feeds the autocomplete on the physical-entities editor (see spectre.core.atlas.entity_history_for_microproject).
    """
    repo = microprojects.get_repository(microproject.slug)
    tips = microprojects.branch_tips(repo)
    return atlas_core.entity_history_for_microproject(repo, tips)


@router.delete("/{slug}")
def delete_microproject(confirm_name: str, microproject: Microproject = Depends(require_role("owner"))) -> dict:
    """Irreversible: deletes the microproject's database rows and its whole on-disk Follow repository
    (every experiment's history). ``confirm_name`` must match the microproject's name exactly - the
    frontend already asks the owner to type it, this is the same guard enforced server-side so a
    raw API call can't skip it.
    """
    if confirm_name.strip() != microproject.name:
        raise HTTPException(status_code=422, detail="le nom saisi ne correspond pas au nom du projet")
    microprojects.delete(microproject)
    return {"status": "ok"}
