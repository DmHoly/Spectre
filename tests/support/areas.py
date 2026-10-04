"""Couche stratégique (plugin areas) : projets corporate, thématiques, objectifs. Les routes
d'écriture sont réservées à un administrateur - le premier compte créé."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def create_area(client: Any, name: str, **fields: Any) -> dict:
    """Un projet corporate (``strategy``, ``description``, ``code_prefix``...) - renvoie le projet."""
    return assert_created(client.post("/api/areas", json={"name": name, **fields}))


def get_area(client: Any, area_slug: str) -> dict:
    """Le projet, ses thématiques et ses objectifs."""
    return assert_ok(client.get(f"/api/areas/{area_slug}"))


def create_thematic(client: Any, area_slug: str, name: str, **fields: Any) -> dict:
    """Une thématique du projet corporate ``area_slug`` - renvoie la thématique."""
    return assert_created(client.post(f"/api/areas/{area_slug}/thematics", json={"name": name, **fields}))


def create_objective(client: Any, area_slug: str, title: str, **fields: Any) -> dict:
    """Un objectif du projet (``weight``, ``target``, ``validated_by``...) - renvoie l'objectif."""
    return assert_created(client.post(f"/api/areas/{area_slug}/objectives", json={"title": title, **fields}))


def set_area_team(client: Any, area_slug: str, team_slug: str | None) -> dict:
    """Rattache le projet à l'équipe ``team_slug`` (``None`` : à aucune) - réservé à
    l'administrateur : PATCH /api/areas/{area_slug} {team}. Renvoie le projet."""
    return assert_ok(client.patch(f"/api/areas/{area_slug}", json={"team": team_slug}))
