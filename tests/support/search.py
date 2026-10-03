"""Recherche de la barre du haut (plugin search)."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def search(client: Any, q: str, types: str | None = None) -> list[dict]:
    """GET /api/search - ``[{type, label, detail, badge, url}]``."""
    return assert_ok(client.get("/api/search", params={"q": q, **({"types": types} if types else {})}))
