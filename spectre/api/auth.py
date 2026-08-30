"""Account creation and sessions. Cookie-based (see :mod:`spectre.core.security`), not JWT - a
session can be revoked server-side by deleting its row, which a stateless token can't offer
without extra machinery this app doesn't need.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..core import accounts
from ..core.security import SESSION_COOKIE, SESSION_LIFETIME
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


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
    _set_session_cookie(response, accounts.create_session(user.id))
    return _user_payload(user)


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
