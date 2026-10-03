"""Corps des requêtes du cahier de données : un instantané à prendre, une vue à ajouter ou à modifier."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SnapshotRequest(BaseModel):
    hook: str  # la clé d'un type de données de caractérisation
    wafers: list[str] = []
    refresh: bool = False


class EntryInput(BaseModel):
    title: str
    snapshot_id: str
    component: str
    options: dict[str, Any] = {}
    note: str | None = None
    objective: str | None = None
    in_report: bool = True


class EntryUpdate(BaseModel):
    """Lu avec ``exclude_unset`` : seuls les champs envoyés changent (``objective`` vide ou nul :
    plus d'objectif)."""

    title: str | None = None
    snapshot_id: str | None = None
    component: str | None = None
    options: dict[str, Any] | None = None
    note: str | None = None
    objective: str | None = None
    in_report: bool | None = None
    position: int | None = None  # la place de la vue dans le cahier, à partir de 0
