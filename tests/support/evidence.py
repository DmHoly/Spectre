"""Preuves d'une étude (plugin evidence) : chaque aide encapsule une route et vérifie son code de
succès ; ``post_*`` renvoient la réponse telle quelle, pour en vérifier un refus. Les écritures
renvoient la preuve ; ``if_match`` envoie l'en-tête ``If-Match`` (la version affichée)."""

from __future__ import annotations

from typing import Any

from .attachments import upload_file
from .http import assert_created, assert_ok


def evidence_url(slug: str, ref: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{ref}/evidence"


def _headers(if_match: str | None) -> dict:
    return {"If-Match": f'"{if_match}"'} if if_match else {}


def upload_image(client: Any, slug: str, name: str = "mesure.png") -> str:
    """Une image collée dans le formulaire de preuve (POST .../attachments, purpose=evidence) - renvoie son id."""
    return upload_file(client, slug, "evidence", name)["id"]


def post_evidence(client: Any, slug: str, ref: str, description: str = "Mesure", *, if_match: str | None = None, **fields: Any) -> Any:
    body = {"description": description, "source": "labo", **fields}
    return client.post(evidence_url(slug, ref), json=body, headers=_headers(if_match))


def add_evidence(client: Any, slug: str, ref: str, description: str = "Mesure", **fields: Any) -> dict:
    """POST /evidence - renvoie la preuve créée (``id`` : l'id de la preuve)."""
    return assert_created(post_evidence(client, slug, ref, description, **fields))


def list_evidence(client: Any, slug: str, ref: str, version: str | None = None) -> list[dict]:
    """GET /evidence - les preuves de la pointe, ou de la version ``version``."""
    return assert_ok(client.get(evidence_url(slug, ref), params={"version": version} if version else {}))


def evidence_by_id(client: Any, slug: str, ref: str, version: str | None = None) -> dict[str, dict]:
    return {evidence["id"]: evidence for evidence in list_evidence(client, slug, ref, version)}


def put_annotations(client: Any, slug: str, ref: str, evidence_id: str, annotations: list[dict], *, if_match: str | None = None) -> Any:
    return client.put(f"{evidence_url(slug, ref)}/{evidence_id}/annotations", json={"annotations": annotations}, headers=_headers(if_match))


def annotate(client: Any, slug: str, ref: str, evidence_id: str, annotations: list[dict], **kwargs: Any) -> dict:
    """PUT /evidence/{id}/annotations - renvoie la preuve."""
    return assert_ok(put_annotations(client, slug, ref, evidence_id, annotations, **kwargs))
