"""Comptes et sessions (plugin accounts) : un même ``TestClient`` ne porte qu'une session à la
fois, ces aides passent d'un compte à l'autre."""

from __future__ import annotations

import re
from typing import Any

from .http import assert_created, assert_ok

PASSWORD = "supersecret"


def logout(client: Any) -> None:
    response = client.delete("/api/sessions/current")
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"


def signup(client: Any, email: str, name: str = "T", password: str = PASSWORD) -> dict:
    """Crée le compte ``email`` et laisse le client connecté dessus (la session en cours, s'il y
    en a une, est d'abord fermée) - renvoie le compte."""
    logout(client)
    return assert_created(client.post("/api/users", json={"email": email, "password": password, "name": name}))


def login(client: Any, email: str, password: str = PASSWORD) -> dict:
    """Ouvre une session sur ``email`` - renvoie le compte."""
    logout(client)
    return assert_created(client.post("/api/sessions", json={"email": email, "password": password}))["user"]


def me(client: Any) -> dict:
    return assert_ok(client.get("/api/users/me"))


def switch_user(client: Any, email: str, name: str = "T", password: str = PASSWORD) -> dict:
    """Passe sur le compte ``email`` : s'y connecte s'il existe déjà, le crée sinon."""
    logout(client)
    response = client.post("/api/sessions", json={"email": email, "password": password})
    if response.status_code == 201:
        return response.json()["user"]
    return signup(client, email, name=name, password=password)


def link_token(body: str, param: str) -> str:
    """Le jeton d'un lien envoyé par e-mail (``.../reinitialiser?token=...``,
    ``.../inscription?invitation=...``)."""
    match = re.search(rf"[?&]{param}=([^\s&]+)", body)
    assert match, f"aucun lien avec {param}= dans : {body}"
    return match.group(1)
