"""Le corps d'une promotion (et de son aperçu) : la structure promue, la référence visée, le pourquoi."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..experiments.schemas import REFERENCE_NUMBER_PATTERN
from ..references.service import MAX_NAME_LENGTH, MAX_TEXT_LENGTH


class NewReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field("", max_length=MAX_NAME_LENGTH)
    description: str = Field("", max_length=MAX_TEXT_LENGTH)


class PromotionRequest(BaseModel):
    """La structure : une version d'étude (``version_id``, la pointe de la piste sinon) et, pour un
    split, sa variante (``variant``, à partir de 0). La référence : ``reference`` (une existante) ou
    ``new_reference`` (une nouvelle) - aucune des deux : celle que la promotion propose (dont part
    l'étude), sinon une nouvelle à nommer. ``parent`` : la version dont elle dérive (automatique
    sinon). ``note`` : pourquoi cette structure devient la référence. ``follow`` : une fois promue,
    la nouvelle version devient la référence suivie de l'étude (``study``) ou de l'étude et de toute
    sa branche (``branch``) - ``None`` : l'étude garde sa référence."""

    model_config = ConfigDict(extra="forbid")

    microproject: str
    experiment_id: str
    version_id: str | None = None
    variant: int | None = Field(None, ge=0, le=999)
    reference: str | None = Field(None, max_length=200)
    new_reference: NewReference | None = None
    parent: str | None = Field(None, max_length=12, pattern=REFERENCE_NUMBER_PATTERN)
    note: str = Field("", max_length=MAX_TEXT_LENGTH)
    follow: Literal["study", "branch"] | None = None
