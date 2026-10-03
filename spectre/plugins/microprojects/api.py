"""Microprojects and membership: the only "who can see/do what" concept in Spectre. Every other
router sits behind :func:`spectre.plugins.microprojects.deps.require_role` for a microproject
resolved here. The invitation a signup link carries: :mod:`.invitations_api`.

The experiment counts of a list of µprojets are not computed here: the front composes them from
``GET /api/experiment-stats`` (plugin experiments).
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ...kernel import mail
from ...kernel.errors import Forbidden, InvalidInput
from ...kernel.http import created
from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from . import service as microprojects
from .deps import require_role
from .invitations_api import router as invitations_router
from .service import Invitation, Microproject

router = APIRouter(prefix="/api", tags=["microprojects"])
router.include_router(invitations_router)
page_router = APIRouter()

Role = Literal["viewer", "editor", "owner"]


class CreateMicroprojectRequest(BaseModel):
    name: str
    description: str = ""
    area: str | None = None  # slug du projet corporate (par défaut : « Non classé »)
    thematic: str | None = None  # slug d'une thématique de ce projet


class MicroprojectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    area: str | None = None  # slug du projet corporate
    thematic: str | None = None  # slug d'une thématique de ce projet ; null : sans thématique


class MemberRequest(BaseModel):
    email: str
    role: Role


class MemberPatch(BaseModel):
    role: Role


class _Places:
    """The projects and thématiques, read once per request: ``{slug, name}`` of each µprojet's."""

    def __init__(self) -> None:
        self._areas = {area.id: area for area in areas.list_all()}
        self._thematics = {thematic.id: thematic for thematic in areas.list_thematics()}

    @staticmethod
    def _ref(item) -> dict | None:
        return {"slug": item.slug, "name": item.name} if item else None

    def area(self, microproject: Microproject) -> dict | None:
        return self._ref(self._areas.get(microproject.management_area_id))

    def thematic(self, microproject: Microproject) -> dict | None:
        return self._ref(self._thematics.get(microproject.thematic_id))


def _payloads(rows: list[tuple[Microproject, str | None]]) -> list[dict]:
    """``(µprojet, rôle de l'appelant)`` -> la ressource complète."""
    places = _Places()
    owners = microprojects.owners_by_microproject([microproject.id for microproject, _ in rows])
    return [
        {
            "id": microproject.id,
            "slug": microproject.slug,
            "code": microproject.code,
            "name": microproject.name,
            "description": microproject.description,
            "role": role,
            "area": places.area(microproject),
            "thematic": places.thematic(microproject),
            "owners": owners[microproject.id],
        }
        for microproject, role in rows
    ]


def _payload(microproject: Microproject, user: User) -> dict:
    return _payloads([(microproject, microprojects.role_for(microproject.id, user.id))])[0]


def _summaries(found: list[Microproject]) -> list[dict]:
    """The reduced fields a company-wide lookup shows (search, number): any signed-in user sees
    them, each µprojet's page keeps its own access rules."""
    places = _Places()
    return [{"slug": m.slug, "code": m.code, "name": m.name, "area": places.area(m)} for m in found]


def _url(microproject: Microproject) -> str:
    return f"/api/microprojects/{microproject.slug}"


def _invitation_payload(invitation: Invitation) -> dict:
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "created_at": invitation.created_at,
        "expires_at": invitation.expires_at,
    }


def _send_invitation(microproject: Microproject, invitation: Invitation, token: str, inviter: User) -> None:
    link = f"{mail.base_url()}/inscription?invitation={token}"
    mail.send_email(
        invitation.email,
        f"Invitation à rejoindre « {microproject.name} » sur Spectre",
        f"{inviter.name} vous invite à rejoindre le µprojet « {microproject.name} » sur Spectre.\n\n"
        f"Pour rejoindre le µprojet, ouvrez ce lien (valable 14 jours) :\n{link}",
    )


# -- µprojets ---------------------------------------------------------------------------------------


@router.get("/microprojects")
def list_microprojects(
    user: User = Depends(current_user),
    scope: Literal["mine", "all"] = "mine",
    area: str | None = None,
    thematic: str | None = None,
    q: str | None = Query(None, max_length=80),
    limit: int = Query(8, ge=1, le=50),
    code: str | None = Query(None, max_length=40),
) -> list[dict]:
    """The caller's µprojets (``scope=all``: every µprojet, admins only), of one project and one of
    its thématiques with ``area`` / ``thematic``. ``q`` (by number or name, best first, at most
    ``limit``) and ``code`` (a number however it's typed) look across the whole company and return
    reduced fields - they combine with no other filter."""
    if q is not None or code is not None:
        if scope != "mine" or area or thematic:
            raise InvalidInput("?q= et ?code= ne se combinent pas avec ?scope=, ?area= ni ?thematic=")
        if code is not None:
            try:
                return _summaries([microprojects.get_by_code(code)])
            except microprojects.MicroprojectNotFoundError:
                return []
        return _summaries(microprojects.search(q, limit=limit))

    if scope == "all":
        if not user.is_admin:
            raise Forbidden("la liste de tous les µprojets est réservée à un administrateur")
        roles = {microproject.id: role for microproject, role in microprojects.list_for_user(user.id)}
        rows = [(microproject, roles.get(microproject.id)) for microproject in microprojects.list_all()]
    else:
        rows = microprojects.list_for_user(user.id)
    if thematic and not area:
        raise InvalidInput("?thematic= se lit dans un projet : précisez ?area=")
    if area:
        area_id = areas.get_by_slug(area).id
        thematic_id = areas.get_thematic(area_id, thematic).id if thematic else None
        rows = [
            (m, role) for m, role in rows if m.management_area_id == area_id and (thematic_id is None or m.thematic_id == thematic_id)
        ]
    return _payloads(rows)


@router.post("/microprojects", status_code=201)
def create_microproject(body: CreateMicroprojectRequest, response: Response, user: User = Depends(current_user)) -> dict:
    microproject = microprojects.create(body.name, body.description, owner_id=user.id, area=body.area, thematic=body.thematic)
    created(response, _url(microproject))
    return _payloads([(microproject, "owner")])[0]


@router.get("/microprojects/{microproject_slug}")
def get_microproject(microproject: Microproject = Depends(require_role("viewer")), user: User = Depends(current_user)) -> dict:
    return _payload(microproject, user)


@router.patch("/microprojects/{microproject_slug}")
def update_microproject(microproject_slug: str, body: MicroprojectPatch, user: User = Depends(current_user)) -> dict:
    """Rename it, or move it to another project / thématique - its owners and the admins."""
    return _payload(microprojects.update(microproject_slug, user, body.model_dump(exclude_unset=True)), user)


@router.delete("/microprojects/{microproject_slug}", status_code=204)
def delete_microproject(confirm_name: str, microproject: Microproject = Depends(require_role("owner"))) -> Response:
    """Irreversible: the µprojet and its whole on-disk Follow repository (every experiment's
    history). ``confirm_name`` must match its name exactly."""
    microprojects.delete(microproject, confirm_name)
    return Response(status_code=204)


# -- membres ----------------------------------------------------------------------------------------


@router.get("/microprojects/{microproject_slug}/members")
def list_members(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return microprojects.list_members(microproject.id)


@router.post("/microprojects/{microproject_slug}/members", status_code=201)
def add_member(body: MemberRequest, response: Response, microproject: Microproject = Depends(require_role("owner"))) -> dict:
    """Add an existing account - 404 ``no_account`` otherwise: the page then offers to invite it."""
    member = microprojects.add_member(microproject, body.email, body.role)
    created(response, f"{_url(microproject)}/members/{member['id']}")
    return member


@router.patch("/microprojects/{microproject_slug}/members/{user_id}")
def change_member_role(user_id: int, body: MemberPatch, microproject: Microproject = Depends(require_role("owner"))) -> dict:
    return microprojects.change_member_role(microproject, user_id, body.role)


@router.delete("/microprojects/{microproject_slug}/members/{user_id}", status_code=204)
def remove_member(user_id: int, microproject: Microproject = Depends(require_role("owner"))) -> Response:
    microprojects.remove_member(microproject, user_id)
    return Response(status_code=204)


# -- invitations ------------------------------------------------------------------------------------


@router.get("/microprojects/{microproject_slug}/invitations")
def list_invitations(microproject: Microproject = Depends(require_role("owner"))) -> list[dict]:
    return [_invitation_payload(invitation) for invitation in microprojects.list_invitations(microproject.id)]


@router.post("/microprojects/{microproject_slug}/invitations", status_code=201)
def invite(body: MemberRequest, microproject: Microproject = Depends(require_role("owner")), user: User = Depends(current_user)) -> dict:
    """Invite an address by e-mail (a signup link, or a sign-in one if it already has an account).
    Without ``Location``: an invitation has no route of its own, it is read in the list."""
    invitation, token = microprojects.create_invitation(microproject, body.email, body.role, invited_by=user.id)
    _send_invitation(microproject, invitation, token, user)
    return _invitation_payload(invitation)


@router.delete("/microprojects/{microproject_slug}/invitations/{invitation_id}", status_code=204)
def cancel_invitation(invitation_id: int, microproject: Microproject = Depends(require_role("owner"))) -> Response:
    microprojects.cancel_invitation(microproject.id, invitation_id)
    return Response(status_code=204)


@router.get("/microprojets/recherche-fdl")
def search_fdl(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> list[dict]:
    """Transitoire, jusqu'à GET /api/wafers?fdl= (plugin wafers) : les études dont une plaque porte
    la FDL tapée, dans les µprojets dont l'appelant est membre."""
    from ..wafers import fdl, service as plates

    return fdl.search(q, plates.visible_entries(user.id))


# -- pages ------------------------------------------------------------------------------------------


@page_router.get("/p/{code}")
def microproject_by_code(code: str, request: Request) -> RedirectResponse:
    """Raccourci à partager : /p/Nat_0004 (ou /p/Nat4) -> la page de ce µprojet. Hors session : la
    connexion d'abord - un anonyme n'apprend pas quels numéros existent."""
    try:
        current_user(request)
    except HTTPException:
        return RedirectResponse(f"/connexion?suite={quote(request.url.path)}", status_code=302)
    try:
        microproject = microprojects.get_by_code(code)
    except microprojects.MicroprojectNotFoundError:
        return RedirectResponse(f"/?introuvable={quote(code)}", status_code=302)
    return RedirectResponse(f"/microprojets/{microproject.slug}", status_code=302)


# "projet" was renamed to "µprojet" (URL: /microprojets) - keep old bookmarks working.
@page_router.get("/projets/{rest:path}")
def legacy_projet_redirect(rest: str):
    return RedirectResponse(f"/microprojets/{rest}", status_code=308)
