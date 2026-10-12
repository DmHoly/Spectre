"""Les corps des requêtes des références : en créer une, la renommer ou la décrire (y publier une
version : le plugin promotion)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .service import MAX_NAME_LENGTH, MAX_TEXT_LENGTH


class ReferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., max_length=MAX_NAME_LENGTH)
    description: str = Field("", max_length=MAX_TEXT_LENGTH)


class ReferenceChanges(BaseModel):
    """Absent (ou ``null``), un champ ne change pas."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
