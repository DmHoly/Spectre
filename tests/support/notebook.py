"""Cahier de données (plugin notebook) : instantanés d'un µprojet et vues du cahier d'une étude.
Les aides ``post_*``, ``patch_*`` et ``delete_*`` renvoient la réponse telle quelle (pour en vérifier
un refus) ; les autres vérifient leur code de succès. ``if_match`` envoie l'en-tête ``If-Match``."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok


def snapshots_url(slug: str) -> str:
    return f"/api/microprojects/{slug}/snapshots"


def entries_url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}/notebook-entries"


def _headers(if_match: str | None) -> dict:
    return {"If-Match": f'"{if_match}"'} if if_match else {}


def post_snapshot(client: Any, slug: str, hook: str = "eqe", wafers: tuple[str, ...] | list[str] = ("W12-A3", "W12-A4"), **fields: Any) -> Any:
    return client.post(snapshots_url(slug), json={"hook": hook, "wafers": list(wafers), **fields})


def take_snapshot(client: Any, slug: str, hook: str = "eqe", wafers: tuple[str, ...] | list[str] = ("W12-A3", "W12-A4")) -> dict:
    """POST /snapshots - renvoie l'instantané (``snapshot_id`` et le jeu de données)."""
    return assert_created(post_snapshot(client, slug, hook, wafers))


def get_snapshot(client: Any, slug: str, snapshot_id: str) -> Any:
    return client.get(f"{snapshots_url(slug)}/{snapshot_id}")


def entries(client: Any, slug: str, experiment_id: str, version: str | None = None) -> list[dict]:
    """Les vues du cahier (de la pointe, ou de ``version``)."""
    return assert_ok(client.get(entries_url(slug, experiment_id), params={"version": version} if version else {}))


def post_entry(client: Any, slug: str, experiment_id: str, *, if_match: str | None = None, **body: Any) -> Any:
    return client.post(entries_url(slug, experiment_id), json=body, headers=_headers(if_match))


def add_entry(
    client: Any, slug: str, experiment_id: str, snapshot_id: str, *, title: str = "Vue", component: str = "table", if_match: str | None = None, **fields: Any
) -> dict:
    """POST /notebook-entries - renvoie la vue ajoutée."""
    response = post_entry(client, slug, experiment_id, if_match=if_match, title=title, snapshot_id=snapshot_id, component=component, **fields)
    return assert_created(response)


def patch_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None, **changes: Any) -> Any:
    return client.patch(f"{entries_url(slug, experiment_id)}/{entry_id}", json=changes, headers=_headers(if_match))


def update_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None, **changes: Any) -> dict:
    """PATCH /notebook-entries/{entry_id} (``position`` pour la déplacer) - renvoie la vue."""
    return assert_ok(patch_entry(client, slug, experiment_id, entry_id, if_match=if_match, **changes))


def delete_entry(client: Any, slug: str, experiment_id: str, entry_id: str, *, if_match: str | None = None) -> Any:
    return client.delete(f"{entries_url(slug, experiment_id)}/{entry_id}", headers=_headers(if_match))
