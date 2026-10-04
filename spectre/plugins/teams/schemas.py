"""Les corps des requêtes du plugin teams."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TeamRole = Literal["manager", "member"]


class TeamCreate(BaseModel):
    name: str


class TeamPatch(BaseModel):
    name: str | None = None


class TeamMemberCreate(BaseModel):
    email: str
    role: TeamRole = "member"


class TeamMemberPatch(BaseModel):
    role: TeamRole
