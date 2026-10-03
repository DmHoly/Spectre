"""The other end of an invitation e-mail (``/inscription?invitation=<token>``): read it without a
session, then accept it once signed in - with a new account or an existing one, as long as its
address is the one invited. Included in :data:`spectre.plugins.microprojects.api.router`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...kernel.errors import Forbidden, NotFound
from ..accounts import service as accounts
from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as microprojects

router = APIRouter(prefix="/invitations", tags=["invitations"])

_INVALID = "cette invitation est invalide ou a expiré"


def _pending(token: str) -> dict:
    invitation = microprojects.get_invitation(token)
    if invitation is None:
        raise NotFound(_INVALID)
    return invitation


@router.get("/{token}")
def get_invitation(token: str) -> dict:
    """Public: the signup page reads it before any account exists. ``account_exists`` tells it to
    offer signing in rather than signing up - only to whoever holds the token, i.e. the invitee."""
    invitation = _pending(token)
    return {
        "email": invitation["email"],
        "microproject_name": invitation["microproject_name"],
        "account_exists": accounts.get_by_email(invitation["email"]) is not None,
    }


@router.post("/{token}/acceptance", status_code=201)
def accept_invitation(token: str, response: Response, user: User = Depends(current_user)) -> dict:
    invitation = _pending(token)
    if not microprojects.accept_invitation(token, user.id, user.email):
        raise Forbidden("cette invitation est adressée à une autre adresse e-mail", code="email_mismatch")
    microproject = microprojects.get_by_id(invitation["microproject_id"])
    response.headers["Location"] = f"/api/microprojects/{microproject.slug}/members/{user.id}"
    return {"microproject": {"slug": microproject.slug, "name": microproject.name}, "role": invitation["role"]}
