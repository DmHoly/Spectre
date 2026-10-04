"""Les corps des requêtes des références : en créer une, la renommer ou la décrire, y publier une
version."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..experiments.schemas import REFERENCE_NUMBER_PATTERN
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


class VersionPublish(BaseModel):
    """La version Follow à publier : une piste du µprojet (sa pointe, ou ``version_id``), et
    facultativement la version de la référence dont elle dérive (``parent``, « 1.1 »)."""

    model_config = ConfigDict(extra="forbid")

    microproject: str
    experiment_id: str
    version_id: str | None = None
    note: str = Field("", max_length=MAX_TEXT_LENGTH)
    parent: str | None = Field(None, max_length=12, pattern=REFERENCE_NUMBER_PATTERN)
