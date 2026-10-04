"""L'atlas d'un projet corporate (plugin atlas)."""

from __future__ import annotations

from typing import Any

from .http import assert_ok

# Le projet corporate système, où arrive tout µprojet créé sans rattachement.
UNCLASSIFIED = "non-classe"


def atlas(client: Any, area_slug: str = UNCLASSIFIED) -> dict:
    """GET /api/areas/{area_slug}/atlas."""
    return assert_ok(client.get(f"/api/areas/{area_slug}/atlas"))


def atlas_microproject(client: Any, slug: str, area_slug: str = UNCLASSIFIED) -> dict:
    """Le nœud du µprojet ``slug`` dans l'atlas."""
    return next(p for p in atlas(client, area_slug)["microprojects"] if p["slug"] == slug)
