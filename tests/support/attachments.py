"""Fichiers téléversés d'un µprojet (plugin attachments)."""

from __future__ import annotations

from typing import Any

from .http import PNG_1PX, assert_created


def attachments_url(slug: str) -> str:
    return f"/api/microprojects/{slug}/attachments"


def post_attachment(client: Any, slug: str, purpose: str = "structure", name: str = "schema.png", content: Any = PNG_1PX, content_type: str = "image/png") -> Any:
    """POST /attachments, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post(attachments_url(slug), data={"purpose": purpose}, files={"file": (name, content, content_type)})


def upload_file(client: Any, slug: str, purpose: str = "structure", name: str = "schema.png", **fields: Any) -> dict:
    """POST /attachments : une image (PNG 1x1 par défaut) - renvoie la ressource créée."""
    return assert_created(post_attachment(client, slug, purpose, name, **fields))
