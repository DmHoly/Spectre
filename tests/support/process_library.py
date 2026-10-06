"""Les bibliothèques à plat (``/api/saved-structures``, ``/api/step-presets``, ``/api/tech-bricks``) :
un helper par route, et les corps d'un élément de chaque collection."""

from __future__ import annotations

from typing import Any

from support.http import assert_created, assert_ok
from support.structures import deposition, etch, substrate

COLLECTIONS = ("saved-structures", "step-presets", "tech-bricks")

PGAN_STEPS = [deposition("PGaN", "GaN", thickness_nm=50)]


def saved_structure(name: str, **fields: Any) -> dict:
    return {"name": name, "substrate": substrate(), "steps": PGAN_STEPS, **fields}


def step_preset(name: str, *, kind: str = "deposition", recipe: str = "CVD Conformal", **fields: Any) -> dict:
    """Un préset d'étape : par défaut un dépôt de 20 nm de SiO2 (``kind="etch"`` : une gravure de
    10 nm) qui nomme ``recipe`` ; ``step=`` donne une autre étape entière."""
    step = deposition(name, "SiO2", recipe=recipe, thickness_nm=20) if kind == "deposition" else etch(name, recipe=recipe, depth_nm=10)
    return {"name": name, "step": step, **fields}


def legacy_step_preset(name: str, *, kind: str = "deposition", recipe: str = "CVD Conformal") -> dict:
    """Un préset de l'ancienne forme, qui ne nommait qu'une recette (avant les présets entiers)."""
    return {"name": name, "payload": {"kind": kind, "recipe": recipe}}


def tech_brick(name: str, **fields: Any) -> dict:
    return {"name": name, "steps": PGAN_STEPS, **fields}


BODIES = {"saved-structures": saved_structure, "step-presets": step_preset, "tech-bricks": tech_brick}


def create_item(client: Any, collection: str, body: dict, *, scope: str = "microproject", microproject: str | None = None) -> dict:
    """Crée l'élément ``body`` dans ``collection`` ; ``microproject`` pour la portée du même nom."""
    return assert_created(client.post(f"/api/{collection}", json={**body, "scope": scope, "microproject": microproject}))


def list_items(client: Any, collection: str, **params: Any) -> list[dict]:
    """``params`` : ``microproject``, ``scope``."""
    return assert_ok(client.get(f"/api/{collection}", params=params))


def get_item(client: Any, collection: str, item_id: str) -> dict:
    return assert_ok(client.get(f"/api/{collection}/{item_id}"))


def update_item(client: Any, collection: str, item_id: str, **changes: Any) -> dict:
    return assert_ok(client.patch(f"/api/{collection}/{item_id}", json=changes))


def delete_item(client: Any, collection: str, item_id: str) -> None:
    response = client.delete(f"/api/{collection}/{item_id}")
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"
    assert response.content == b""


def names(items: list[dict], scope: str | None = None) -> list[str]:
    return [item["name"] for item in items if scope is None or item["scope"] == scope]


def by_name(items: list[dict], name: str) -> dict:
    return next(item for item in items if item["name"] == name)
