"""Projects and membership - the data-access layer over the ``projects``/``memberships`` tables,
plus where each project's own Follow repository and StructureForge recipe library live on disk.
Follow and StructureForge never know a "project" exists; this is the one place that maps a slug
to the paths they're given.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import data_dir, get_conn

ROLE_ORDER = {"viewer": 0, "editor": 1, "owner": 2}


class ProjectNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Project:
    id: int
    slug: str
    name: str
    description: str
    created_by: int


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"], slug=row["slug"], name=row["name"], description=row["description"], created_by=row["created_by"]
    )


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "projet"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def create(name: str, description: str, *, owner_id: int) -> Project:
    name = name.strip()
    if not name:
        raise ValueError("le nom du projet est obligatoire")
    with get_conn() as conn:
        slug = _unique_slug(conn, _slugify(name))
        cursor = conn.execute(
            "INSERT INTO projects (slug, name, description, created_by) VALUES (?, ?, ?, ?)",
            (slug, name, description.strip(), owner_id),
        )
        project_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO memberships (project_id, user_id, role) VALUES (?, ?, 'owner')",
            (project_id, owner_id),
        )
    project_dir(slug)  # create the on-disk home for this project's Follow repo/recipes upfront
    return Project(id=project_id, slug=slug, name=name, description=description.strip(), created_by=owner_id)


def get_by_slug(slug: str) -> Project:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise ProjectNotFoundError(slug)
    return _project_from_row(row)


def list_for_user(user_id: int) -> list[tuple[Project, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT projects.*, memberships.role AS role FROM projects "
            "JOIN memberships ON memberships.project_id = projects.id "
            "WHERE memberships.user_id = ? ORDER BY projects.created_at DESC",
            (user_id,),
        ).fetchall()
    return [(_project_from_row(row), row["role"]) for row in rows]


def role_for(project_id: int, user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM memberships WHERE project_id = ? AND user_id = ?", (project_id, user_id)
        ).fetchone()
    return row["role"] if row else None


def list_members(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT users.id, users.name, users.email, memberships.role FROM memberships "
            "JOIN users ON users.id = memberships.user_id WHERE memberships.project_id = ? "
            "ORDER BY users.name",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_member(project_id: int, email: str, role: str) -> None:
    from . import accounts

    if role not in ROLE_ORDER:
        raise ValueError(f"rôle inconnu : {role!r}")
    user = accounts.get_by_email(email)
    if user is None:
        raise ValueError(f"aucun compte n'existe avec l'adresse {email!r}")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO memberships (project_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (project_id, user.id, role),
        )


def remove_member(project_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM memberships WHERE project_id = ? AND user_id = ?", (project_id, user_id))


def project_dir(slug: str) -> Path:
    path = data_dir() / "projects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def follow_repo_path(slug: str) -> Path:
    return project_dir(slug) / "follow"


def recipes_path(slug: str) -> Path:
    return project_dir(slug) / "recipes.json"


def get_repository(slug: str):
    """A fresh ``follow.storage.repository.Repository`` for this project, reloaded from disk on
    every call - Spectre serves many projects from one process, so nothing is cached in memory
    the way ``follow_api`` (one repository per process) can afford to.
    """
    import follow

    return follow.Repository(follow_repo_path(slug))


def get_recipe_store(slug: str):
    from structureforge.core.recipe_store import RecipeStore

    return RecipeStore(recipes_path(slug))
