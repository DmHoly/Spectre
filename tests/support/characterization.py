"""Types de données de caractérisation (plugin characterization)."""

from __future__ import annotations

from typing import Any

from .http import assert_ok

DATA_TYPES = "/api/characterization/data-types"


def list_data_types(client: Any, **filters: Any) -> list[dict]:
    """``category``, ``status``, ``by_wafer`` : les filtres de la collection."""
    return assert_ok(client.get(DATA_TYPES, params=filters))


def list_categories(client: Any) -> list[dict]:
    return assert_ok(client.get("/api/characterization/categories"))


def get_data_type(client: Any, key: str) -> Any:
    return client.get(f"{DATA_TYPES}/{key}")


def run_query(client: Any, key: str, parameters: dict[str, list[str]] | None = None, *, refresh: bool = False) -> Any:
    return client.post(f"{DATA_TYPES}/{key}/queries", json={"parameters": parameters or {}, "refresh": refresh})


def get_chart(client: Any, key: str, chart_key: str) -> Any:
    return client.get(f"{DATA_TYPES}/{key}/charts/{chart_key}")
