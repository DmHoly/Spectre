"""Corps des requêtes du plugin lots."""

from __future__ import annotations

from pydantic import BaseModel


class LotCreate(BaseModel):
    code: str | None = None  # vide = LOT-0001...
    title: str = ""
    description: str = ""
    priority: str = ""  # P10, P20...
    started_on: str | None = None
    forecast_exit_on: str | None = None
    wafers: list[str] = []
    thematic_ids: list[int] = []


class LotPatch(BaseModel):
    """Les champs envoyés seulement (``exclude_unset``) ; une date à ``null`` est effacée."""

    code: str = ""
    title: str = ""
    description: str = ""
    priority: str = ""
    status: str = ""
    started_on: str | None = None
    forecast_exit_on: str | None = None
    exited_on: str | None = None  # fin déclarée
    hold_reason: str = ""


class LotWafersAdd(BaseModel):
    lasermarks: list[str]


class LotThematics(BaseModel):
    thematic_ids: list[int]
