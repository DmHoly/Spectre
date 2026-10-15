"""Plaques (plugin wafers) : la collection, le passeport d'une plaque et sa vie en ligne."""

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


def get_tracking(client: Any, wafer_key: str) -> Any:
    """GET /api/wafers/{wafer_key}/tracking, tel quel (la réponse, pour en vérifier un refus)."""
    return client.get(f"/api/wafers/{wafer_key}/tracking")


def refresh_tracking(client: Any, wafer_key: str) -> Any:
    """POST /api/wafers/{wafer_key}/tracking/refresh : relit les bases quoi qu'il arrive."""
    return client.post(f"/api/wafers/{wafer_key}/tracking/refresh")


def lookup_wafers(client: Any, lasermarks: list[str]) -> dict:
    """GET /api/wafers/lookup?lasermark=… : dans Spectre puis dans la base, toutes d'un coup."""
    return assert_ok(client.get("/api/wafers/lookup", params={"lasermark": lasermarks}))


def create_records(client: Any, lasermarks: list[str]) -> dict:
    """POST /api/wafer-records : les fiches de ces plaques (créées, ou rendues telles quelles)."""
    response = client.post("/api/wafer-records", json={"lasermarks": lasermarks})
    assert response.status_code == 201, response.text
    return response.json()


def delete_record(client: Any, wafer_key: str) -> Any:
    """DELETE /api/wafer-records/{wafer_key}, tel quel (la réponse, pour en vérifier un refus)."""
    return client.delete(f"/api/wafer-records/{wafer_key}")
