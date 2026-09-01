"""Projects and membership - the data-access layer over the ``projects``/``memberships`` tables,
plus where each project's own Follow repository, saved structures, and step presets live on disk.
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
    project_dir(slug)  # create the on-disk home for this project's Follow repo/structures upfront
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


def add_member(project_id: int, project_name: str, email: str, role: str, *, invited_by: int) -> str:
    """Add ``email`` to the project directly if they already have an account (returns
    ``"added"``), or create a two-week invitation and e-mail them a signup link otherwise
    (returns ``"invited"``) - see :func:`accept_invitation` for the other end of that link.
    """
    from . import accounts
    from . import email as email_module
    from . import security

    if role not in ROLE_ORDER:
        raise ValueError(f"rôle inconnu : {role!r}")
    email = email.strip().lower()
    user = accounts.get_by_email(email)
    if user is not None:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO memberships (project_id, user_id, role) VALUES (?, ?, ?) "
                "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
                (project_id, user.id, role),
            )
        return "added"

    token = security.new_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO invitations (token, project_id, email, role, invited_by, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (token, project_id, email, role, invited_by, security.invitation_expiry()),
        )
    inviter = accounts.get_by_id(invited_by)
    link = f"{email_module.base_url()}/inscription?invitation={token}"
    email_module.send_email(
        email,
        f"Invitation à rejoindre « {project_name} » sur Spectre",
        f"{inviter.name if inviter else 'Un membre'} vous invite à rejoindre le projet "
        f"« {project_name} » sur Spectre.\n\n"
        f"Pour créer votre compte et rejoindre le projet, ouvrez ce lien (valable 14 jours) :\n{link}",
    )
    return "invited"


def remove_member(project_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM memberships WHERE project_id = ? AND user_id = ?", (project_id, user_id))


def list_invitations(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT token, email, role, created_at FROM invitations WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_invitation(project_id: int, token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM invitations WHERE project_id = ? AND token = ?", (project_id, token))


def get_invitation(token: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT invitations.token, invitations.email, invitations.role, invitations.project_id, "
            "projects.name AS project_name FROM invitations JOIN projects ON projects.id = invitations.project_id "
            "WHERE invitations.token = ? AND invitations.expires_at > datetime('now')",
            (token,),
        ).fetchone()
    return dict(row) if row else None


def accept_invitation(token: str, user_id: int, user_email: str) -> bool:
    """Consume an invitation for a just-registered user - only if its email matches the one the
    invitation was addressed to (a token alone isn't proof of that email address, since it
    travels inside a plain URL). Returns whether it was accepted.
    """
    invitation = get_invitation(token)
    if invitation is None or invitation["email"] != user_email.strip().lower():
        return False
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO memberships (project_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (invitation["project_id"], user_id, invitation["role"]),
        )
        conn.execute("DELETE FROM invitations WHERE token = ?", (token,))
    return True


def delete(project: Project) -> None:
    """Permanently delete a project: its database rows (memberships and pending invitations
    cascade via the foreign keys) and the on-disk directory holding its Follow repository, saved
    structures, and step presets - there is no undo, this is real experiment history.
    """
    import shutil

    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project.id,))
    shutil.rmtree(project_dir(project.slug), ignore_errors=True)


def project_dir(slug: str) -> Path:
    path = data_dir() / "projects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def follow_repo_path(slug: str) -> Path:
    return project_dir(slug) / "follow"


def structures_path(slug: str) -> Path:
    return project_dir(slug) / "structures.json"


def shared_structures_path() -> Path:
    """Not inside any project's own directory - visible from every project, see
    :mod:`spectre.core.structure_library`.
    """
    return data_dir() / "structures_partagees.json"


def get_structure_store(slug: str):
    from .structure_library import StructureLibraryStore

    return StructureLibraryStore(structures_path(slug))


def get_shared_structure_store():
    from .structure_library import StructureLibraryStore

    return StructureLibraryStore(shared_structures_path())


def get_repository(slug: str):
    """A fresh ``follow.storage.repository.Repository`` for this project, reloaded from disk on
    every call - Spectre serves many projects from one process, so nothing is cached in memory
    the way ``follow_api`` (one repository per process) can afford to.
    """
    import follow

    return follow.Repository(follow_repo_path(slug))


def step_presets_path(slug: str) -> Path:
    return project_dir(slug) / "presets_etapes.json"


def shared_step_presets_path() -> Path:
    """Not inside any project's own directory - visible from every project, see
    :mod:`spectre.core.step_presets` (same split as :func:`shared_structures_path`).
    """
    return data_dir() / "presets_etapes_partages.json"


def get_step_preset_store(slug: str):
    from .step_presets import StepPresetStore

    return StepPresetStore(step_presets_path(slug))


def get_shared_step_preset_store():
    from .step_presets import StepPresetStore

    return StepPresetStore(shared_step_presets_path())
