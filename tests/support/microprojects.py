"""µprojets et leurs membres (plugin microprojects)."""

from __future__ import annotations

from typing import Any

from .accounts import login, signup, switch_user
from .http import assert_created, assert_ok


def create_microproject(client: Any, name: str = "Projet", **fields: Any) -> dict:
    """Un µprojet créé par le compte connecté (qui en devient propriétaire). ``fields`` :
    ``description``, ``management_area_slug``, ``thematique_slug``..."""
    return assert_created(client.post("/api/microprojets", json={"name": name, **fields}))


def move_microproject(client: Any, area_slug: str, microproject_slug: str, thematic_slug: str | None = None) -> dict:
    """Rattache un µprojet au projet corporate ``area_slug`` (et à l'une de ses thématiques) :
    PATCH /api/microprojects/{microproject_slug} - renvoie le µprojet."""
    body = {"area": area_slug, "thematic": thematic_slug}
    return assert_ok(client.patch(f"/api/microprojects/{microproject_slug}", json=body))


def signup_with_microproject(client: Any, email: str, microproject_name: str = "Projet", *, name: str = "T") -> str:
    """Crée le compte ``email``, puis un µprojet dont il est propriétaire - renvoie son slug."""
    signup(client, email, name=name)
    return create_microproject(client, microproject_name)["slug"]


def add_member(client: Any, slug: str, email: str, role: str = "viewer") -> dict:
    """Ajoute ``email`` au µprojet (le compte connecté doit en être propriétaire) - directement
    s'il a déjà un compte, par une invitation sinon."""
    return assert_created(client.post(f"/api/microprojets/{slug}/members", json={"email": email, "role": role}))


def join_as(client: Any, slug: str, email: str, *, owner: str, role: str = "viewer", name: str = "V") -> None:
    """Fait entrer ``email`` dans le µprojet ``slug`` avec le rôle ``role`` (ajouté par
    ``owner``) et laisse le client connecté sur ce compte. Le compte est créé d'abord s'il le faut :
    sans compte, ``/members`` enverrait une invitation au lieu de l'ajouter."""
    switch_user(client, email, name=name)
    login(client, owner)
    add_member(client, slug, email, role)
    login(client, email)
