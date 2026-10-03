"""Accounts, sessions and passwords over HTTP. Cookie-based (see :mod:`spectre.plugins.accounts.security`),
not JWT - a session can be revoked server-side by deleting its row, which a stateless token can't
offer without extra machinery this app doesn't need.

Joining a microproject from an invitation is not part of signing up: the signup page creates the
account (``POST /api/users``), then accepts the invitation (``POST /api/invitations/{token}/acceptance``,
plugin microprojects).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel

from . import service as accounts
from .deps import current_user
from .security import SESSION_COOKIE, SESSION_LIFETIME, session_cookie_secure

router = APIRouter(prefix="/api", tags=["accounts"])

ME = "/api/users/me"
CURRENT_SESSION = "/api/sessions/current"


class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class CreateSessionRequest(BaseModel):
    email: str
    password: str


class UpdateMeRequest(BaseModel):
    name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetCompletion(BaseModel):
    token: str
    password: str


def _user_payload(user: accounts.User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin}


def _open_session(response: Response, user: accounts.User) -> str:
    """Open a session for ``user`` and hand its cookie to the browser - returns its expiry."""
    token, expires_at = accounts.create_session(user.id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=session_cookie_secure(),
    )
    return expires_at


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax", secure=session_cookie_secure())


@router.post("/users", status_code=201)
def create_user(body: CreateUserRequest, response: Response) -> dict:
    """Sign up - and sign in: the new account leaves with its session."""
    user = accounts.register(body.email, body.password, body.name)
    _open_session(response, user)
    response.headers["Location"] = ME
    return _user_payload(user)


@router.post("/sessions", status_code=201)
def create_session(body: CreateSessionRequest, response: Response) -> dict:
    user = accounts.authenticate(body.email, body.password)
    expires_at = _open_session(response, user)
    response.headers["Location"] = CURRENT_SESSION
    return {"user": _user_payload(user), "expires_at": expires_at}


@router.delete("/sessions/current", status_code=204)
def delete_current_session(request: Request) -> Response:
    """Public: without a session there is nothing to close, and the answer is the same."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        accounts.delete_session(token)
    response = Response(status_code=204)
    _clear_session_cookie(response)
    return response


@router.get("/users/me")
def get_me(user: accounts.User = Depends(current_user)) -> dict:
    return _user_payload(user)


@router.patch("/users/me")
def update_me(body: UpdateMeRequest, user: accounts.User = Depends(current_user)) -> dict:
    if body.name is not None:
        user = accounts.update_name(user.id, body.name)
    return _user_payload(user)


@router.put("/users/me/password", status_code=204)
def change_password(body: ChangePasswordRequest, user: accounts.User = Depends(current_user)) -> Response:
    accounts.change_password(user.id, body.current_password, body.new_password)
    # change_password() already deleted every session for this user, including the one making
    # this request - clear the now-dead cookie so the browser doesn't keep sending it.
    response = Response(status_code=204)
    _clear_session_cookie(response)
    return response


@router.post("/password-resets", status_code=202)
def request_password_reset(body: PasswordResetRequest, background: BackgroundTasks) -> Response:
    """Always the same empty 202, whether or not the address has an account - confirming or
    denying an account's existence to an anonymous caller is its own small information leak. The
    lookup and the e-mail happen after the response, so its timing says nothing either.
    """
    background.add_task(accounts.send_password_reset, body.email)
    return Response(status_code=202)


@router.post("/password-resets/completions", status_code=204)
def complete_password_reset(body: PasswordResetCompletion) -> Response:
    accounts.reset_password(body.token, body.password)
    return Response(status_code=204)
