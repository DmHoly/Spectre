"""Analyses de plaques (plugin meta_analysis) : une référence, des plaques à lui comparer, une conclusion."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def create_analysis(client: Any, title: str, wafers: list[str], question: str = "") -> dict:
    return assert_created(client.post("/api/analyses", json={"title": title, "wafers": wafers, "question": question}))


def update_analysis(client: Any, analysis_id: int, **values: Any) -> Any:
    """PATCH /api/analyses/{id}, tel quel (la réponse, pour en vérifier un refus)."""
    return client.patch(f"/api/analyses/{analysis_id}", json=values)


def list_analyses(client: Any, **params: Any) -> list[dict]:
    """GET /api/analyses (``wafer``)."""
    return assert_ok(client.get("/api/analyses", params=params))


def lasermarks(analysis: dict) -> list[str]:
    """Les plaques d'une analyse, la référence d'abord."""
    return [wafer["lasermark"] for wafer in analysis["wafers"]]
