"""Corps des requêtes de la galerie d'images externes."""

from __future__ import annotations

from pydantic import BaseModel


class ImageSetInput(BaseModel):
    title: str | None = None
    note: str | None = None
    entity_index: int | None = None  # une variante d'une campagne ; toute l'étude sinon
    image_paths: list[str]
    pinned_index: int = 0


class ImageSetUpdate(BaseModel):
    pinned_index: int
