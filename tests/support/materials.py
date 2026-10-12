"""Matériaux de l'instance (plugin materials) : le document de la page, et ce qu'en voit le constructeur."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def material_library(client: Any) -> dict:
    """GET /api/material-library - le document."""
    return assert_ok(client.get("/api/material-library"))


def saved(client: Any, document: dict) -> dict:
    """PUT /api/material-library - renvoie le document relu."""
    return assert_ok(client.put("/api/material-library", json=document))


def editable(document: dict) -> dict:
    """Ce que la page renvoie : le document lu, sans ce qui n'est que de lecture."""
    return {key: document[key] for key in ("revision", "materials", "gradients")}


def two_stops(low: str, high: str, generic_x: float = 0.5) -> dict:
    return {"stops": [{"x": 0.0, "color": low}, {"x": 1.0, "color": high}], "generic_x": generic_x}
