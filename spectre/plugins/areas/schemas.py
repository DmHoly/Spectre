"""Les corps des requêtes du plugin areas. Un ``PATCH`` ne change que les champs envoyés
(``exclude_unset``)."""

from __future__ import annotations

from pydantic import BaseModel


class AreaCreate(BaseModel):
    name: str
    description: str = ""
    strategy: str = ""
    code_prefix: str | None = None  # préfixe des numéros de ses µprojets (« Nat ») ; déduit du nom s'il manque


class AreaPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    strategy: str | None = None
    objectives_period: str | None = None
    code_prefix: str | None = None


class ThematicCreate(BaseModel):
    name: str
    description: str = ""


class ThematicPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class ObjectiveCreate(BaseModel):
    title: str
    detail: str = ""
    target: str = ""
    weight: float | None = None  # chiffre du bonus, 0 à 100 % ; None = pas encore fixé
    achieved: bool = False
    validated_by: str | None = None  # slug du µprojet qui l'a validé


class ObjectivePatch(BaseModel):
    title: str | None = None
    detail: str | None = None
    target: str | None = None
    weight: float | None = None
    achieved: bool | None = None
    validated_by: str | None = None
