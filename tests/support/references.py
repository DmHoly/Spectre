"""Références de structure (plugin references) : en créer une, y promouvoir une version (plugin
promotion), lire son évolution. Chaque aide encapsule une route et vérifie son code de succès ; les ``post_*`` renvoient
la réponse telle quelle (pour en vérifier un refus)."""

from __future__ import annotations

from typing import Any

from .http import assert_created, assert_ok

REFERENCES = "/api/references"


def reference_url(slug: str) -> str:
    return f"{REFERENCES}/{slug}"


def references(client: Any, q: str | None = None) -> list[dict]:
    """GET /api/references (``q`` : recherche)."""
    return assert_ok(client.get(REFERENCES, params={"q": q} if q is not None else {}))


def post_reference(client: Any, name: str, description: str = "") -> Any:
    return client.post(REFERENCES, json={"name": name, "description": description})


def create_reference(client: Any, name: str = "Epitaxie standard", description: str = "") -> dict:
    """POST /api/references - renvoie la référence (sans version)."""
    return assert_created(post_reference(client, name, description))


def get_reference(client: Any, slug: str) -> dict:
    return assert_ok(client.get(reference_url(slug)))


def patch_reference(client: Any, slug: str, **changes: Any) -> Any:
    return client.patch(reference_url(slug), json=changes)


def delete_reference(client: Any, slug: str) -> Any:
    return client.delete(reference_url(slug))


PROMOTIONS = "/api/promotions"


def post_promotion(client: Any, microproject: str, experiment_id: str, **fields: Any) -> Any:
    """POST /api/promotions - ``fields`` : ``reference``, ``new_reference``, ``version_id``,
    ``variant``, ``note``, ``parent``."""
    return client.post(PROMOTIONS, json={"microproject": microproject, "experiment_id": experiment_id, **fields})


def preview_promotion(client: Any, microproject: str, experiment_id: str, **fields: Any) -> dict:
    """POST /api/promotions/preview - ce que donnerait la promotion (les règles, le numéro)."""
    return assert_ok(client.post(f"{PROMOTIONS}/preview", json={"microproject": microproject, "experiment_id": experiment_id, **fields}))


def post_version(client: Any, slug: str, microproject: str, experiment_id: str, **fields: Any) -> Any:
    """Promouvoir dans la référence ``slug`` (POST /api/promotions) - ``fields`` : ``version_id``,
    ``variant``, ``note``, ``parent``."""
    return post_promotion(client, microproject, experiment_id, reference=slug, **fields)


def publish(client: Any, slug: str, microproject: str, experiment_id: str, **fields: Any) -> dict:
    """Promeut la pointe de la piste (ou ``version_id``) dans ``slug`` - renvoie la version créée (``number``)."""
    return assert_created(post_version(client, slug, microproject, experiment_id, **fields))


def version_graph(client: Any, slug: str) -> dict:
    """GET /api/references/{slug}/versions - ``{reference, lanes, nodes, edges}``."""
    return assert_ok(client.get(f"{reference_url(slug)}/versions"))


def get_version(client: Any, slug: str, number: str) -> dict:
    return assert_ok(client.get(f"{reference_url(slug)}/versions/{number}"))


def published_from(client: Any, microproject: str) -> list[dict]:
    """GET /api/reference-versions?microproject= - les versions publiées depuis ce µprojet."""
    return assert_ok(client.get("/api/reference-versions", params={"microproject": microproject}))


def origin(reference: str, version: str) -> dict:
    """Le champ ``reference_origin`` d'un lancement."""
    return {"reference": reference, "version": version}
