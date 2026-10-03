"""Microprojects and membership: the only "who can see/do what" concept in Spectre. Every other
router (structures, experiments) sits behind :func:`spectre.plugins.microprojects.deps.require_role`
for a microproject resolved here. The invitation a signup link carries: :mod:`.invitations_api`.

The experiment counts on each µprojet, and the topbar's FDL search, read plugins listed above this
one (experiments, wafers) through imports inside the functions that need them.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..accounts.deps import current_user, require_admin
from ..accounts.service import User
from ..areas import service as management
from ..areas.service import ManagementAreaNotFoundError, ThematicNotFoundError
from . import service as microprojects
from .deps import require_role
from .invitations_api import router as invitations_router
from .service import Microproject

router = APIRouter(prefix="/api", tags=["microprojects"])
router.include_router(invitations_router)
page_router = APIRouter()


class CreateMicroprojectRequest(BaseModel):
    name: str
    description: str = ""
    management_area_slug: str | None = None  # which corporate project it belongs to (default: « Non classé »)
    thematique_slug: str | None = None  # one of that project's thématiques (optional)


class AddMemberRequest(BaseModel):
    email: str
    role: str


def _area_ref(management_area_id: int | None) -> dict | None:
    if management_area_id is None:
        return None
    try:
        area = management.get_by_id(management_area_id)
    except ManagementAreaNotFoundError:
        return None
    return {"slug": area.slug, "name": area.name}


def _thematic_ref(thematic_id: int | None) -> dict | None:
    if thematic_id is None:
        return None
    try:
        thematic = management.get_thematic_by_id(thematic_id)
    except ThematicNotFoundError:
        return None
    return {"slug": thematic.slug, "name": thematic.name}


def _microproject_payload(microproject: Microproject, role: str, owners: list[dict] | None = None) -> dict:
    """``owners`` when the caller already batched them (:func:`microprojects.owners_by_microproject`)."""
    from ..experiments.repository import experiment_counts

    running, concluded = experiment_counts(microproject.slug)
    if owners is None:
        owners = microprojects.owners_by_microproject([microproject.id])[microproject.id]
    return {
        "id": microproject.id,
        "slug": microproject.slug,
        "code": microproject.code,
        "name": microproject.name,
        "description": microproject.description,
        "role": role,
        "running_count": running,
        "concluded_count": concluded,
        "management_area": _area_ref(microproject.management_area_id),
        "thematique": _thematic_ref(microproject.thematic_id),
        "owners": owners,
    }


@router.get("/microprojets")
def list_microprojects(user: User = Depends(current_user)) -> list[dict]:
    mine = microprojects.list_for_user(user.id)
    owners = microprojects.owners_by_microproject([microproject.id for microproject, _ in mine])
    return [_microproject_payload(microproject, role, owners[microproject.id]) for microproject, role in mine]


@router.post("/microprojets", status_code=201)
def create_microproject(body: CreateMicroprojectRequest, user: User = Depends(current_user)) -> dict:
    area_id = thematic_id = None
    if body.management_area_slug:
        try:
            area_id = management.get_by_slug(body.management_area_slug).id
        except ManagementAreaNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"projet {body.management_area_slug!r} introuvable") from exc
        if body.thematique_slug:
            try:
                thematic_id = management.get_thematic(area_id, body.thematique_slug).id
            except ThematicNotFoundError as exc:
                raise HTTPException(status_code=404, detail=f"thématique {body.thematique_slug!r} introuvable") from exc
    try:
        microproject = microprojects.create(
            body.name, body.description, owner_id=user.id, management_area_id=area_id, thematic_id=thematic_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _microproject_payload(microproject, "owner")


@router.get("/microprojets/recherche")
def search_microprojects(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> list[dict]:
    """The topbar search: µprojets by number (« Nat 4 ») or name, for any signed-in user - the same
    company-wide visibility as the corporate-project pages (each µprojet's page keeps its own
    access rules)."""
    return [
        {
            "slug": p.slug,
            "code": p.code,
            "name": p.name,
            "management_area": _area_ref(p.management_area_id),
        }
        for p in microprojects.search(q)
    ]


@router.get("/microprojets/recherche-fdl")
def search_fdl(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> list[dict]:
    """The topbar search, FDL side: experiences whose wafers carry the FDL typed (« 1234 », « FDL-1234 »)
    - only in the microprojects the caller is a member of, like any experience."""
    from ..wafers import fdl, service as plates

    return fdl.search(q, plates.visible_entries(user.id))


@router.get("/microprojets/tous")
def list_all_microprojects(_admin: User = Depends(require_admin)) -> list[dict]:
    """Every µprojet, whichever project/thématique it sits in - admin only, for the "move a µprojet
    here" picker on the corporate-project page."""
    return [
        {
            "slug": p.slug,
            "code": p.code,
            "name": p.name,
            "management_area": _area_ref(p.management_area_id),
            "thematique": _thematic_ref(p.thematic_id),
        }
        for p in microprojects.list_all()
    ]


@router.get("/microprojets/code/{code}")
def find_by_code(code: str, user: User = Depends(current_user)) -> dict:
    """A µprojet by its number, however it's typed (« Nat_0004 », « Nat 4 », « nat4 ») - for the
    « aller au µprojet » fields; any signed-in user (its page then applies its own access rules)."""
    try:
        microproject = microprojects.get_by_code(code)
    except microprojects.MicroprojectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"aucun µprojet numéroté « {code} »") from exc
    return {"slug": microproject.slug, "code": microproject.code, "name": microproject.name}


@router.get("/microprojets/{slug}")
def get_microproject(microproject: Microproject = Depends(require_role("viewer")), user: User = Depends(current_user)) -> dict:
    role = microprojects.role_for(microproject.id, user.id)
    return _microproject_payload(microproject, role)


@router.get("/microprojets/{slug}/members")
def list_members(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return microprojects.list_members(microproject.id)


@router.post("/microprojets/{slug}/members", status_code=201)
def add_member(
    body: AddMemberRequest, microproject: Microproject = Depends(require_role("owner")), user: User = Depends(current_user)
) -> dict:
    try:
        status = microprojects.add_member(microproject.id, microproject.name, body.email, body.role, invited_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": status, "members": microprojects.list_members(microproject.id), "invitations": microprojects.list_invitations(microproject.id)}


@router.get("/microprojets/{slug}/invitations")
def list_invitations(microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    return microprojects.list_invitations(microproject.id)


@router.delete("/microprojets/{slug}/invitations/{token}")
def cancel_invitation(token: str, microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    microprojects.cancel_invitation(microproject.id, token)
    return microprojects.list_invitations(microproject.id)


@router.delete("/microprojets/{slug}/members/{user_id}")
def remove_member(user_id: int, microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    if user_id == microproject.created_by:
        raise HTTPException(status_code=400, detail="impossible de retirer la personne qui a créé le projet")
    microprojects.remove_member(microproject.id, user_id)
    return microprojects.list_members(microproject.id)


@router.delete("/microprojets/{slug}")
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


@page_router.get("/p/{code}")
def microproject_by_code(code: str):
    """Raccourci à partager : /p/Nat_0004 (ou /p/Nat4) -> la page de ce µprojet."""
    try:
        microproject = microprojects.get_by_code(code)
    except microprojects.MicroprojectNotFoundError:
        return RedirectResponse(url=f"/?introuvable={quote(code)}", status_code=302)
    return RedirectResponse(url=f"/microprojets/{microproject.slug}", status_code=302)


# "projet" was renamed to "µprojet" (URL: /microprojets) - keep old bookmarks working.
@page_router.get("/projets/{rest:path}")
def legacy_projet_redirect(rest: str):
    return RedirectResponse(f"/microprojets/{rest}", status_code=308)
