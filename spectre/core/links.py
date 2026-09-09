"""Cross-microproject links: the one relationship allowed to reach across two microprojects' otherwise
isolated Follow repositories - see the schema comment in :mod:`spectre.core.db` for why this
can't be a Follow reference or ride in ``Experiment.metadata`` the way same-microproject links do.
Two kinds, both symmetric (``a``/``b`` order carries no meaning): a microproject link ("these two
microprojects' work relates") and an entity link ("this physical sample relates to that one"), each
just a row plus an optional note explaining why.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import get_conn


@dataclass(frozen=True)
class MicroprojectLink:
    id: int
    microproject_a_id: int
    microproject_b_id: int
    note: str
    created_by: int
    created_at: str


@dataclass(frozen=True)
class EntityRef:
    microproject_slug: str
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


def _microproject_link_from_row(row) -> MicroprojectLink:
    return MicroprojectLink(
        id=row["id"],
        microproject_a_id=row["microproject_a_id"],
        microproject_b_id=row["microproject_b_id"],
        note=row["note"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _entity_link_from_row(row) -> EntityLink:
    return EntityLink(
        id=row["id"],
        a=EntityRef(row["a_microproject_slug"], row["a_experience_id"], row["a_entity_index"]),
        b=EntityRef(row["b_microproject_slug"], row["b_experience_id"], row["b_entity_index"]),
        note=row["note"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def create_microproject_link(microproject_a_id: int, microproject_b_id: int, *, note: str, created_by: int) -> MicroprojectLink:
    if microproject_a_id == microproject_b_id:
        raise ValueError("un projet ne peut pas être lié à lui-même")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM microproject_links WHERE (microproject_a_id = ? AND microproject_b_id = ?) "
            "OR (microproject_a_id = ? AND microproject_b_id = ?)",
            (microproject_a_id, microproject_b_id, microproject_b_id, microproject_a_id),
        ).fetchone()
        if existing is not None:
            raise ValueError("ces deux projets sont déjà liés")
        cursor = conn.execute(
            "INSERT INTO microproject_links (microproject_a_id, microproject_b_id, note, created_by) VALUES (?, ?, ?, ?)",
            (microproject_a_id, microproject_b_id, note.strip(), created_by),
        )
        row_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM microproject_links WHERE id = ?", (row_id,)).fetchone()
    return _microproject_link_from_row(row)


def list_microproject_links(microproject_id: int) -> list[MicroprojectLink]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM microproject_links WHERE microproject_a_id = ? OR microproject_b_id = ? ORDER BY created_at",
            (microproject_id, microproject_id),
        ).fetchall()
    return [_microproject_link_from_row(row) for row in rows]


def list_all_microproject_links(microproject_ids: list[int]) -> list[MicroprojectLink]:
    """Every link with at least one end inside ``microproject_ids`` - what the atlas needs to draw
    links between clusters it's actually showing, in one query rather than one per microproject."""
    if not microproject_ids:
        return []
    placeholders = ",".join("?" * len(microproject_ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM microproject_links WHERE microproject_a_id IN ({placeholders}) OR microproject_b_id IN ({placeholders})",
            [*microproject_ids, *microproject_ids],
        ).fetchall()
    return [_microproject_link_from_row(row) for row in rows]


def delete_microproject_link(link_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM microproject_links WHERE id = ?", (link_id,))


def get_microproject_link(link_id: int) -> MicroprojectLink | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microproject_links WHERE id = ?", (link_id,)).fetchone()
    return _microproject_link_from_row(row) if row else None


def create_entity_link(a: EntityRef, b: EntityRef, *, note: str, created_by: int) -> EntityLink:
    if a == b:
        raise ValueError("une entité ne peut pas être liée à elle-même")
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO entity_links "
            "(a_microproject_slug, a_experience_id, a_entity_index, b_microproject_slug, b_experience_id, b_entity_index, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (a.microproject_slug, a.experience_id, a.entity_index, b.microproject_slug, b.experience_id, b.entity_index, note.strip(), created_by),
        )
        row_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM entity_links WHERE id = ?", (row_id,)).fetchone()
    return _entity_link_from_row(row)


def list_all_entity_links(microproject_slugs: list[str]) -> list[EntityLink]:
    if not microproject_slugs:
        return []
    placeholders = ",".join("?" * len(microproject_slugs))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM entity_links WHERE a_microproject_slug IN ({placeholders}) OR b_microproject_slug IN ({placeholders})",
            [*microproject_slugs, *microproject_slugs],
        ).fetchall()
    return [_entity_link_from_row(row) for row in rows]


def get_entity_link(link_id: int) -> EntityLink | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM entity_links WHERE id = ?", (link_id,)).fetchone()
    return _entity_link_from_row(row) if row else None


def delete_entity_link(link_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM entity_links WHERE id = ?", (link_id,))
