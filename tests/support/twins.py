"""Plaques jumelles (plugin twins) : les plaques de même structure qu'une ligne du comparateur."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def get_twins(client: Any, item: str, max_variations: int | None = None) -> Any:
    """GET /api/wafer-twins, tel quel (la réponse, pour en vérifier un refus)."""
    params: dict[str, Any] = {"item": item}
    if max_variations is not None:
        params["max_variations"] = max_variations
    return client.get("/api/wafer-twins", params=params)


def find_twins(client: Any, item: str, max_variations: int | None = None) -> dict:
    return assert_ok(get_twins(client, item, max_variations))


def lasermarks(found: dict) -> list[str]:
    """Les plaques trouvées, dans l'ordre de la réponse."""
    return [twin["lasermark"] for twin in found["twins"]]
