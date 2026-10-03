"""Les corps des requêtes du plugin links. Un µprojet y est désigné par son slug, une étude par sa
piste (``experiment_id``)."""

from __future__ import annotations

from pydantic import BaseModel


class MicroprojectLinkCreate(BaseModel):
    a: str
    b: str
    note: str = ""


class EntityRefInput(BaseModel):
    microproject: str
    experiment_id: str
    entity_index: int


class EntityLinkCreate(BaseModel):
    a: EntityRefInput
    b: EntityRefInput
    note: str = ""
