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


def get_fdl(client: Any, fdl: str) -> dict:
    """GET /api/fdls/{fdl} : les plaques d'une FDL, lues dans la source courante."""
    return assert_ok(client.get(f"/api/fdls/{fdl}"))


def put_fdl_wafers(client: Any, fdl: str, lasermarks: list[str]) -> Any:
    """PUT /api/fdls/{fdl}/wafers, tel quel (la réponse, pour en vérifier un refus)."""
    return client.put(f"/api/fdls/{fdl}/wafers", json={"lasermarks": lasermarks})
