from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict


class PluginPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class RowPatch(BaseModel):
    """Les cellules d'une ligne à écrire : colonne -> texte, nombre, booléen ou ``null``."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, Union[bool, int, float, str, None]]
