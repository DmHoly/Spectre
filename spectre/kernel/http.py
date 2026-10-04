"""Petits helpers HTTP des routes : la ``Location`` d'une création, l'``ETag`` d'une ressource
versionnée et la version qu'un ``If-Match`` attend."""

from __future__ import annotations

from fastapi import Response


def created(response: Response, location: str) -> None:
    """Une création : ``201`` et l'URL de la ressource créée."""
    response.status_code = 201
    response.headers["Location"] = location


def etag(version: str) -> str:
    return f'"{version}"'


def if_match_version(header: str | None) -> str | None:
    """La version qu'un en-tête ``If-Match`` attend (``"v"``, ``W/"v"`` ou ``v`` nu ; la première
    s'il y en a plusieurs) - ``None`` pour un en-tête absent, vide ou ``*`` (n'importe laquelle)."""
    first = (header or "").split(",")[0].strip().removeprefix("W/").strip('"').strip()
    return None if first in ("", "*") else first
