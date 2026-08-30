"""Account creation and sessions. Cookie-based (see :mod:`spectre.core.security`), not JWT - a
session can be revoked server-side by deleting its row, which a stateless token can't offer
without extra machinery this app doesn't need.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..core import accounts, email as email_module
from ..core.security import SESSION_COOKIE, SESSION_LIFETIME
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    invitation: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class UpdateProfileRequest(BaseModel):
    name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _user_payload(user: accounts.User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
    )


@router.post("/register", status_code=201)
def register(body: RegisterRequest, response: Response) -> dict:
    try:
        user = accounts.register(body.email, body.password, body.name)
    except accounts.EmailAlreadyUsedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    joined_project = None
    if body.invitation:
        from ..core import projects as projects_module

        invitation = projects_module.get_invitation(body.invitation)
        if projects_module.accept_invitation(body.invitation, user.id, user.email):
            joined_project = invitation["project_name"]

    _set_session_cookie(response, accounts.create_session(user.id))
    payload = _user_payload(user)
    payload["joined_project"] = joined_project
    return payload


@router.get("/invitation/{token}")
def get_invitation(token: str) -> dict:
    from ..core import projects as projects_module

    invitation = projects_module.get_invitation(token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="cette invitation est invalide ou a expiré")
    return {"email": invitation["email"], "project_name": invitation["project_name"]}


@router.post("/login")
def login(body: LoginRequest, response: Response) -> dict:
    try:
        user = accounts.authenticate(body.email, body.password)
    except accounts.InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(response, accounts.create_session(user.id))
    return _user_payload(user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        accounts.delete_session(token)
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@router.get("/me")
def me(user: accounts.User = Depends(get_current_user)) -> dict:
    return _user_payload(user)


@router.put("/me")
def update_profile(body: UpdateProfileRequest, user: accounts.User = Depends(get_current_user)) -> dict:
    try:
        updated = accounts.update_name(user.id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _user_payload(updated)


@router.post("/mot-de-passe")
def change_password(
    body: ChangePasswordRequest, request: Request, response: Response, user: accounts.User = Depends(get_current_user)
) -> dict:
    try:
        accounts.change_password(user.id, body.current_password, body.new_password)
    except accounts.InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # change_password() already deleted every session for this user, including the one making
    # this request - clear the now-dead cookie so the browser doesn't keep sending it.
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@router.post("/mot-de-passe-oublie")
def forgot_password(body: ForgotPasswordRequest) -> dict:
    """Always answers the same way whether or not the address has an account - confirming or
    denying an account's existence to an anonymous caller is its own small information leak.
    """
    user = accounts.get_by_email(body.email)
    if user is not None:
        token = accounts.create_password_reset(user.id)
        link = f"{email_module.base_url()}/reinitialiser?token={token}"
        email_module.send_email(
            user.email,
            "Réinitialiser votre mot de passe Spectre",
            f"Bonjour {user.name},\n\n"
            f"Pour choisir un nouveau mot de passe, ouvrez ce lien (valable 1 heure) :\n{link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.",
        )
    return {"status": "ok"}


@router.post("/reinitialiser")
def reset_password(body: ResetPasswordRequest) -> dict:
    try:
        accounts.reset_password(body.token, body.password)
    except accounts.InvalidCredentialsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
