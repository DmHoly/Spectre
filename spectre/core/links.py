"""Cross-project links: the one relationship allowed to reach across two projects' otherwise
isolated Follow repositories - see the schema comment in :mod:`spectre.core.db` for why this
can't be a Follow reference or ride in ``Experiment.metadata`` the way same-project links do.
Two kinds, both symmetric (``a``/``b`` order carries no meaning): a project link ("these two
projects' work relates") and an entity link ("this physical sample relates to that one"), each
just a row plus an optional note explaining why.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import get_conn


@dataclass(frozen=True)
class ProjectLink:
    id: int
    project_a_id: int
    project_b_id: int
    note: str
    created_by: int
    created_at: str


@dataclass(frozen=True)
class EntityRef:
    project_slug: str
    experience_id: str
    entity_index: int


@dataclass(frozen=True)
class EntityLink:
    id: int
    a: EntityRef
    b: EntityRef
    note: str
    created_by: int
    created_at: str


def _project_link_from_row(row) -> ProjectLink:
    return ProjectLink(
        id=row["id"],
        project_a_id=row["project_a_id"],
        project_b_id=row["project_b_id"],
        note=row["note"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _entity_link_from_row(row) -> EntityLink:
    return EntityLink(
        id=row["id"],
        a=EntityRef(row["a_project_slug"], row["a_experience_id"], row["a_entity_index"]),
        b=EntityRef(row["b_project_slug"], row["b_experience_id"], row["b_entity_index"]),
        note=row["note"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def create_project_link(project_a_id: int, project_b_id: int, *, note: str, created_by: int) -> ProjectLink:
    if project_a_id == project_b_id:
        raise ValueError("un projet ne peut pas être lié à lui-même")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM project_links WHERE (project_a_id = ? AND project_b_id = ?) "
            "OR (project_a_id = ? AND project_b_id = ?)",
            (project_a_id, project_b_id, project_b_id, project_a_id),
        ).fetchone()
        if existing is not None:
            raise ValueError("ces deux projets sont déjà liés")
        cursor = conn.execute(
            "INSERT INTO project_links (project_a_id, project_b_id, note, created_by) VALUES (?, ?, ?, ?)",
            (project_a_id, project_b_id, note.strip(), created_by),
        )
        row_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM project_links WHERE id = ?", (row_id,)).fetchone()
    return _project_link_from_row(row)


def list_project_links(project_id: int) -> list[ProjectLink]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM project_links WHERE project_a_id = ? OR project_b_id = ? ORDER BY created_at",
            (project_id, project_id),
        ).fetchall()
    return [_project_link_from_row(row) for row in rows]


def list_all_project_links(project_ids: list[int]) -> list[ProjectLink]:
    """Every link with at least one end inside ``project_ids`` - what the atlas needs to draw
    links between clusters it's actually showing, in one query rather than one per project."""
    if not project_ids:
        return []
    placeholders = ",".join("?" * len(project_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM project_links WHERE project_a_id IN ({placeholders}) OR project_b_id IN ({placeholders})",
            [*project_ids, *project_ids],
        ).fetchall()
    return [_project_link_from_row(row) for row in rows]


def delete_project_link(link_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM project_links WHERE id = ?", (link_id,))


def get_project_link(link_id: int) -> ProjectLink | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM project_links WHERE id = ?", (link_id,)).fetchone()
    return _project_link_from_row(row) if row else None


def create_entity_link(a: EntityRef, b: EntityRef, *, note: str, created_by: int) -> EntityLink:
    if a == b:
        raise ValueError("une entité ne peut pas être liée à elle-même")
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO entity_links "
            "(a_project_slug, a_experience_id, a_entity_index, b_project_slug, b_experience_id, b_entity_index, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (a.project_slug, a.experience_id, a.entity_index, b.project_slug, b.experience_id, b.entity_index, note.strip(), created_by),
        )
        row_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM entity_links WHERE id = ?", (row_id,)).fetchone()
    return _entity_link_from_row(row)


def list_all_entity_links(project_slugs: list[str]) -> list[EntityLink]:
    if not project_slugs:
        return []
    placeholders = ",".join("?" * len(project_slugs))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM entity_links WHERE a_project_slug IN ({placeholders}) OR b_project_slug IN ({placeholders})",
            [*project_slugs, *project_slugs],
        ).fetchall()
    return [_entity_link_from_row(row) for row in rows]


def get_entity_link(link_id: int) -> EntityLink | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM entity_links WHERE id = ?", (link_id,)).fetchone()
    return _entity_link_from_row(row) if row else None


def delete_entity_link(link_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM entity_links WHERE id = ?", (link_id,))
