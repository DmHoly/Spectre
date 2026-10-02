"""Couche stratégique (plugin management) : projets corporate, thématiques, rattachement des
µprojets. Les routes d'écriture sont réservées à un administrateur - le premier compte créé."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def create_area(client: Any, name: str, **fields: Any) -> dict:
    """Un projet corporate (``strategy``, ``description``, ``code_prefix``...)."""
    return assert_created(client.post("/api/management", json={"name": name, **fields}))


def create_thematique(client: Any, area_slug: str, name: str, **fields: Any) -> dict:
    """Une thématique du projet corporate ``area_slug`` - renvoie le projet entier."""
    return assert_created(client.post(f"/api/management/{area_slug}/thematiques", json={"name": name, **fields}))


def move_microproject(client: Any, area_slug: str, microproject_slug: str, thematique_slug: str | None = None) -> dict:
    """Rattache un µprojet au projet corporate ``area_slug`` (et à l'une de ses thématiques)."""
    body = {"microproject_slug": microproject_slug, **({"thematique_slug": thematique_slug} if thematique_slug else {})}
    return assert_ok(client.post(f"/api/management/{area_slug}/microprojets", json=body))
