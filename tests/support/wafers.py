"""Plaques (plugin wafers) : la collection et le passeport d'une plaque."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def list_wafers(client: Any, **params: Any) -> list[dict]:
    """GET /api/wafers (``q``, ``fdl``, ``microproject``)."""
    return assert_ok(client.get("/api/wafers", params=params))


def get_wafer(client: Any, wafer_key: str) -> dict:
    """Le passeport d'une plaque (sa clé, ou son lasermark tel qu'écrit)."""
    return assert_ok(client.get(f"/api/wafers/{wafer_key}"))
