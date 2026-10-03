"""µprojets, leurs membres et leurs invitations (plugin microprojects)."""

from __future__ import annotations

from typing import Any

from .accounts import link_token, login, signup, switch_user
from .http import assert_created, assert_ok


def _url(slug: str) -> str:
    return f"/api/microprojects/{slug}"


def create_microproject(client: Any, name: str = "Projet", **fields: Any) -> dict:
    """Un µprojet créé par le compte connecté (qui en devient propriétaire) : POST /api/microprojects.
    ``fields`` : ``description``, ``area`` (slug du projet corporate), ``thematic``..."""
    return assert_created(client.post("/api/microprojects", json={"name": name, **fields}))


def get_microproject(client: Any, slug: str) -> dict:
    return assert_ok(client.get(_url(slug)))


def list_microprojects(client: Any, **params: Any) -> list[dict]:
    """GET /api/microprojects : les µprojets du compte connecté ; ``scope="all"``, ``area``,
    ``thematic``, ``q``, ``limit``, ``code``."""
    return assert_ok(client.get("/api/microprojects", params=params))


def move_microproject(client: Any, area_slug: str, microproject_slug: str, thematic_slug: str | None = None) -> dict:
    """Rattache un µprojet au projet corporate ``area_slug`` (et à l'une de ses thématiques) :
    PATCH /api/microprojects/{microproject_slug} - renvoie le µprojet."""
    body = {"area": area_slug, "thematic": thematic_slug}
    return assert_ok(client.patch(_url(microproject_slug), json=body))


def delete_microproject(client: Any, slug: str, confirm_name: str) -> Any:
    """DELETE /api/microprojects/{slug}?confirm_name= - renvoie la réponse."""
    return client.delete(_url(slug), params={"confirm_name": confirm_name})


def signup_with_microproject(client: Any, email: str, microproject_name: str = "Projet", *, name: str = "T") -> str:
    """Crée le compte ``email``, puis un µprojet dont il est propriétaire - renvoie son slug."""
    signup(client, email, name=name)
    return create_microproject(client, microproject_name)["slug"]


def members(client: Any, slug: str) -> list[dict]:
    return assert_ok(client.get(f"{_url(slug)}/members"))


def add_member(client: Any, slug: str, email: str, role: str = "viewer") -> dict:
    """Ajoute le compte ``email`` (qui doit exister) au µprojet - le compte connecté doit en être
    propriétaire. Renvoie le membre."""
    return assert_created(client.post(f"{_url(slug)}/members", json={"email": email, "role": role}))


def set_member_role(client: Any, slug: str, user_id: int, role: str) -> Any:
    """PATCH .../members/{user_id} - renvoie la réponse."""
    return client.patch(f"{_url(slug)}/members/{user_id}", json={"role": role})


def remove_member(client: Any, slug: str, user_id: int) -> Any:
    """DELETE .../members/{user_id} - renvoie la réponse."""
    return client.delete(f"{_url(slug)}/members/{user_id}")


def invitations(client: Any, slug: str) -> list[dict]:
    return assert_ok(client.get(f"{_url(slug)}/invitations"))


def invite(client: Any, slug: str, email: str, role: str = "viewer") -> dict:
    """Invite ``email`` par e-mail : POST .../invitations - renvoie l'invitation (sans son jeton)."""
    return assert_created(client.post(f"{_url(slug)}/invitations", json={"email": email, "role": role}))


def invite_and_get_token(client: Any, outbox: list, slug: str, email: str, role: str = "viewer") -> str:
    """Invite ``email`` et renvoie le jeton du lien de l'e-mail parti - le seul endroit où il figure."""
    invite(client, slug, email, role)
    assert outbox[-1].to == email
    return link_token(outbox[-1].body, "invitation")


def join_as(client: Any, slug: str, email: str, *, owner: str, role: str = "viewer", name: str = "V") -> None:
    """Fait entrer ``email`` dans le µprojet ``slug`` avec le rôle ``role`` (ajouté par
    ``owner``) et laisse le client connecté sur ce compte, créé d'abord s'il le faut."""
    switch_user(client, email, name=name)
    login(client, owner)
    add_member(client, slug, email, role)
    login(client, email)
