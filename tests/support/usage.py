"""Utilisation de l'application (plugin usage) : le rapport, et l'horloge de l'enregistreur."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .http import assert_ok


def usage_report(client: Any, **params: Any) -> dict:
    """GET /api/usage - renvoie le rapport."""
    return assert_ok(client.get("/api/usage", params={k: v for k, v in params.items() if v is not None}))


def at(monkeypatch: Any, when: datetime) -> None:
    """Les requêtes suivantes sont comptées à ``when`` (heure locale du serveur)."""
    from spectre.plugins.usage import recorder

    monkeypatch.setattr(recorder, "now", lambda: when)
