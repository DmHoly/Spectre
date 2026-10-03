"""Formulaires d'intention (plugin intent_forms) : la bibliothèque et le formulaire actif d'un
µprojet. Chaque aide encapsule une route et vérifie son code de succès."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok

SIMPLE_FORM_YAML = """
title: Formulaire simple
fields:
  - name: operateur
    label: Opérateur
    type: string
    required: true
"""


def active_path(slug: str) -> str:
    return f"/api/microprojects/{slug}/active-intent-form"


def create_intent_form(
    client: Any, slug: str | None = None, name: str = "Simple", yaml: str = SIMPLE_FORM_YAML, *, scope: str | None = None
) -> dict:
    """Une entrée de la bibliothèque : celle du µprojet ``slug``, ou la bibliothèque partagée
    (``slug`` absent, ou ``scope="shared"``)."""
    scope = scope or ("microproject" if slug else "shared")
    body = {"name": name, "yaml": yaml, "scope": scope, "microproject": slug if scope == "microproject" else None}
    response = client.post("/api/intent-forms", json=body)
    created = assert_created(response)
    assert response.headers["location"] == f"/api/intent-forms/{created['id']}"
    return created


def list_intent_forms(client: Any, **params: Any) -> list[dict]:
    """``params`` : ``microproject``, ``scope``."""
    return assert_ok(client.get("/api/intent-forms", params=params))


def get_intent_form(client: Any, form_id: str) -> dict:
    return assert_ok(client.get(f"/api/intent-forms/{form_id}"))


def update_intent_form(client: Any, form_id: str, **fields: Any) -> dict:
    """``fields`` : ``name``, ``yaml``."""
    return assert_ok(client.patch(f"/api/intent-forms/{form_id}", json=fields))


def delete_intent_form(client: Any, form_id: str) -> None:
    response = client.delete(f"/api/intent-forms/{form_id}")
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"
    assert response.content == b""


def get_active_intent_form(client: Any, slug: str) -> dict:
    return assert_ok(client.get(active_path(slug)))


def activate_intent_form(client: Any, slug: str, form_id: str) -> dict:
    return assert_ok(client.put(active_path(slug), json={"intent_form_id": form_id}))


def deactivate_intent_form(client: Any, slug: str) -> None:
    response = client.delete(active_path(slug))
    assert response.status_code == 204, f"{response.status_code} au lieu de 204 : {response.text}"
    assert response.content == b""


def activate_simple_form(client: Any, slug: str) -> dict:
    """Crée l'entrée « Simple » (une question obligatoire, ``operateur``) dans la bibliothèque du
    µprojet et l'active - renvoie le formulaire actif."""
    created = create_intent_form(client, slug)
    return activate_intent_form(client, slug, created["id"])
