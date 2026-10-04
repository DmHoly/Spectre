"""Liens entre µprojets et entre entités physiques (plugin links). Un µprojet est désigné par son
slug, une entité par ``(slug, piste, index)``."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def entity(microproject: str, experiment_id: str, entity_index: int = 0) -> dict:
    """Un bout de lien d'entité."""
    return {"microproject": microproject, "experiment_id": experiment_id, "entity_index": entity_index}


def post_microproject_link(client: Any, a: str, b: str, note: str = "") -> Any:
    """POST /api/microproject-links, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post("/api/microproject-links", json={"a": a, "b": b, "note": note})


def link_microprojects(client: Any, a: str, b: str, note: str = "") -> dict:
    """Lie les µprojets ``a`` et ``b`` - renvoie le lien."""
    return assert_created(post_microproject_link(client, a, b, note))


def microproject_links(client: Any, **filters: Any) -> list[dict]:
    """GET /api/microproject-links (``microproject=``, ``area=``)."""
    return assert_ok(client.get("/api/microproject-links", params=filters))


def post_entity_link(client: Any, a: dict, b: dict, note: str = "") -> Any:
    """POST /api/entity-links, tel quel - ``a`` et ``b`` : voir :func:`entity`."""
    return client.post("/api/entity-links", json={"a": a, "b": b, "note": note})


def link_entities(client: Any, a: dict, b: dict, note: str = "") -> dict:
    """Lie deux entités (voir :func:`entity`) - renvoie le lien."""
    return assert_created(post_entity_link(client, a, b, note))


def entity_links(client: Any, **filters: Any) -> list[dict]:
    """GET /api/entity-links (``microproject=``, ``area=``)."""
    return assert_ok(client.get("/api/entity-links", params=filters))
