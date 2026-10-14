"""Les corps des requêtes du plugin teams."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TeamRole = Literal["manager", "member"]


class TeamCreate(BaseModel):
    name: str
    color: str | None = None  # #rrggbb ; une couleur de la palette sinon
    badge: str | None = None  # libellé court du badge (4 caractères au plus) ; les initiales sinon


class TeamPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    badge: str | None = None


class TeamMemberCreate(BaseModel):
    email: str
    role: TeamRole = "member"


class TeamMemberPatch(BaseModel):
    role: TeamRole
