"""Comptes et sessions (plugin accounts) : un même ``TestClient`` ne porte qu'une session à la
fois, ces aides passent d'un compte à l'autre."""

from __future__ import annotations

import re
from typing import Any

from .http import assert_created, assert_ok

PASSWORD = "supersecret"


def logout(client: Any) -> None:
    client.post("/api/auth/logout")


def signup(client: Any, email: str, name: str = "T", password: str = PASSWORD, **fields: Any) -> dict:
    """Crée le compte ``email`` et laisse le client connecté dessus (la session en cours, s'il y
    en a une, est d'abord fermée). ``fields`` : le reste du corps, ``invitation`` par exemple."""
    logout(client)
    return assert_created(client.post("/api/auth/register", json={"email": email, "password": password, "name": name, **fields}))


def login(client: Any, email: str, password: str = PASSWORD) -> dict:
    logout(client)
    return assert_ok(client.post("/api/auth/login", json={"email": email, "password": password}))


def switch_user(client: Any, email: str, name: str = "T", password: str = PASSWORD) -> dict:
    """Passe sur le compte ``email`` : s'y connecte s'il existe déjà, le crée sinon."""
    logout(client)
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code == 200:
        return response.json()
    return signup(client, email, name=name, password=password)


def link_token(body: str, param: str) -> str:
    """Le jeton d'un lien envoyé par e-mail (``.../reinitialiser?token=...``,
    ``.../inscription?invitation=...``)."""
    match = re.search(rf"[?&]{param}=([^\s&]+)", body)
    assert match, f"aucun lien avec {param}= dans : {body}"
    return match.group(1)
