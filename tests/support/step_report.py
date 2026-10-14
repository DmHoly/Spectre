"""Commentaires d'étape (plugin step_report) : ``/api/microprojects/{slug}/step-comments``."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def put_comment(client: Any, slug: str, step_id: str, text: str) -> Any:
    """PUT .../step-comments/{step_id}, tel quel (la réponse, pour en vérifier un refus)."""
    return client.put(f"/api/microprojects/{slug}/step-comments/{step_id}", json={"text": text})


def comments(client: Any, slug: str, *step_ids: str) -> dict:
    """GET .../step-comments (``step_id=`` répété) : ``{step_id: commentaire}``."""
    return assert_ok(client.get(f"/api/microprojects/{slug}/step-comments", params={"step_id": list(step_ids)}))["comments"]
