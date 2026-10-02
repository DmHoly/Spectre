"""Lots de fabrication (plugin lots)."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def create_lot(client: Any, code: str | None = None, **fields: Any) -> dict:
    """Un lot (``title``, ``priority``, ``wafers``, ``started_on``...) - sans ``code``, le
    suivant de la numérotation LOT-0001."""
    body = {**({"code": code} if code else {}), **fields}
    return assert_created(client.post("/api/lots", json=body))


def update_lot(client: Any, code: str, **fields: Any) -> dict:
    """PUT /lots/{code} : le lot entier (``code`` compris) tel qu'il doit être après."""
    return assert_ok(client.put(f"/api/lots/{code}", json={"code": code, **fields}))


def get_lot(client: Any, code: str) -> dict:
    return assert_ok(client.get(f"/api/lots/{code}"))
