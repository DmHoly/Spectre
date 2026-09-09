"""The corporate strategy layer: "management areas" are the grands thèmes leadership steers by,
each holding a set of µprojets (:mod:`spectre.core.microprojects`). Thin data-access over the
``management_areas`` table - like :mod:`spectre.core.microprojects` but simpler: an area has no Follow
repo or on-disk home of its own, and access is company-wide (every signed-in user sees every
area; only an admin, ``users.is_admin``, creates/renames one or moves a µprojet between areas).
"""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass

from .db import UNCLASSIFIED_AREA_SLUG, get_conn


class ManagementAreaNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ManagementArea:
    id: int
    slug: str
    name: str
    description: str
    strategy: str
    created_by: int | None


def _from_row(row: sqlite3.Row) -> ManagementArea:
    return ManagementArea(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        strategy=row["strategy"],
        created_by=row["created_by"],
    )


def _slugify(name: str) -> str:
    from .microprojects import slugify

    return slugify(name) or "theme"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug, suffix = base, 2
    while conn.execute("SELECT 1 FROM management_areas WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def list_all() -> list[ManagementArea]:
    # « Non classé » always last; the rest in creation order (the flagship themes keep the order
    # they were seeded in, a later hand-created one lands after them).
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM management_areas ORDER BY (slug = ?), id", (UNCLASSIFIED_AREA_SLUG,)).fetchall()
    return [_from_row(row) for row in rows]


def get_by_slug(slug: str) -> ManagementArea:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM management_areas WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise ManagementAreaNotFoundError(slug)
    return _from_row(row)


def get_by_id(area_id: int) -> ManagementArea:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM management_areas WHERE id = ?", (area_id,)).fetchone()
    if row is None:
        raise ManagementAreaNotFoundError(str(area_id))
    return _from_row(row)


def unclassified() -> ManagementArea:
    return get_by_slug(UNCLASSIFIED_AREA_SLUG)


def create(name: str, description: str = "", strategy: str = "", *, created_by: int) -> ManagementArea:
    name = name.strip()
    if not name:
        raise ValueError("le nom du thème est obligatoire")
    with get_conn() as conn:
        slug = _unique_slug(conn, _slugify(name))
        cursor = conn.execute(
            "INSERT INTO management_areas (slug, name, description, strategy, created_by) VALUES (?, ?, ?, ?, ?)",
            (slug, name, description.strip(), strategy.strip(), created_by),
        )
        return ManagementArea(cursor.lastrowid, slug, name, description.strip(), strategy.strip(), created_by)


def update(area_id: int, *, name: str, description: str, strategy: str) -> ManagementArea:
    name = name.strip()
    if not name:
        raise ValueError("le nom du thème est obligatoire")
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM management_areas WHERE id = ?", (area_id,)).fetchone() is None:
            raise ManagementAreaNotFoundError(str(area_id))
        conn.execute(
            "UPDATE management_areas SET name = ?, description = ?, strategy = ? WHERE id = ?",
            (name, description.strip(), strategy.strip(), area_id),
        )
    return get_by_id(area_id)


def delete(area_id: int) -> None:
    """Remove an area; its µprojets fall back to « Non classé » rather than being deleted. The
    catch-all area itself cannot be removed.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT slug FROM management_areas WHERE id = ?", (area_id,)).fetchone()
        if row is None:
            raise ManagementAreaNotFoundError(str(area_id))
        if row["slug"] == UNCLASSIFIED_AREA_SLUG:
            raise ValueError("le thème « Non classé » ne peut pas être supprimé")
        fallback = conn.execute(
            "SELECT id FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)
        ).fetchone()["id"]
        conn.execute("UPDATE microprojects SET management_area_id = ? WHERE management_area_id = ?", (fallback, area_id))
        conn.execute("DELETE FROM management_areas WHERE id = ?", (area_id,))
