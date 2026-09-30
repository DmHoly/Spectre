"""The corporate strategy layer, a three-level hierarchy:

- **management areas** - the *projets corporate* leadership steers by (Native (PT2), VLC
  (microlink), Nova (PT1)), each with a ranked list of objectives for the coming period;
- **thematics** - the technical thématiques of one project (dopage PGaN, double EBL...);
- **µprojets** (:mod:`spectre.core.microprojects`) - chains of experiments, attached to an area and
  optionally to one of its thematics.

Thin data-access over the ``management_areas`` / ``thematics`` / ``area_objectives`` tables - like
:mod:`spectre.core.microprojects` but simpler: none of these has a Follow repo or on-disk home of
its own, and access is company-wide (every signed-in user sees everything; only an admin,
``users.is_admin``, writes).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .db import UNCLASSIFIED_AREA_SLUG, get_conn

DEFAULT_OBJECTIVES_PERIOD = "6 prochains mois"


class ManagementAreaNotFoundError(Exception):
    pass


class ThematicNotFoundError(Exception):
    pass


class ObjectiveNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ManagementArea:
    id: int
    slug: str
    name: str
    description: str
    strategy: str
    created_by: int | None
    objectives_period: str = DEFAULT_OBJECTIVES_PERIOD


@dataclass(frozen=True)
class Thematic:
    id: int
    management_area_id: int
    slug: str
    name: str
    description: str
    position: int


@dataclass(frozen=True)
class Objective:
    id: int
    management_area_id: int
    title: str
    detail: str
    target: str  # free-text échéance ("T1 2027", "fin mars")
    position: int  # 0 = most important


def _from_row(row: sqlite3.Row) -> ManagementArea:
    return ManagementArea(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        strategy=row["strategy"],
        created_by=row["created_by"],
        objectives_period=row["objectives_period"],
    )


def _thematic_from_row(row: sqlite3.Row) -> Thematic:
    return Thematic(row["id"], row["management_area_id"], row["slug"], row["name"], row["description"], row["position"])


def _objective_from_row(row: sqlite3.Row) -> Objective:
    return Objective(row["id"], row["management_area_id"], row["title"], row["detail"], row["target"], row["position"])


def _slugify(name: str, fallback: str = "projet") -> str:
    from .microprojects import slugify

    return slugify(name) or fallback


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug, suffix = base, 2
    while conn.execute("SELECT 1 FROM management_areas WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def list_all() -> list[ManagementArea]:
    # « Non classé » always last; the rest in creation order (the flagship projects keep the order
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
        raise ValueError("le nom du projet est obligatoire")
    with get_conn() as conn:
        slug = _unique_slug(conn, _slugify(name))
        conn.execute(
            "INSERT INTO management_areas (slug, name, description, strategy, created_by) VALUES (?, ?, ?, ?, ?)",
            (slug, name, description.strip(), strategy.strip(), created_by),
        )
    return get_by_slug(slug)


def update(
    area_id: int, *, name: str, description: str, strategy: str, objectives_period: str | None = None
) -> ManagementArea:
    name = name.strip()
    if not name:
        raise ValueError("le nom du projet est obligatoire")
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM management_areas WHERE id = ?", (area_id,)).fetchone() is None:
            raise ManagementAreaNotFoundError(str(area_id))
        conn.execute(
            "UPDATE management_areas SET name = ?, description = ?, strategy = ? WHERE id = ?",
            (name, description.strip(), strategy.strip(), area_id),
        )
        if objectives_period is not None:
            conn.execute(
                "UPDATE management_areas SET objectives_period = ? WHERE id = ?",
                (objectives_period.strip() or DEFAULT_OBJECTIVES_PERIOD, area_id),
            )
    return get_by_id(area_id)


def delete(area_id: int) -> None:
    """Remove an area; its µprojets fall back to « Non classé » (without thématique) rather than
    being deleted, its thématiques and objectives go with it. The catch-all area itself cannot be
    removed.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT slug FROM management_areas WHERE id = ?", (area_id,)).fetchone()
        if row is None:
            raise ManagementAreaNotFoundError(str(area_id))
        if row["slug"] == UNCLASSIFIED_AREA_SLUG:
            raise ValueError("« Non classé » ne peut pas être supprimé")
        fallback = conn.execute(
            "SELECT id FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)
        ).fetchone()["id"]
        conn.execute(
            "UPDATE microprojects SET management_area_id = ?, thematic_id = NULL WHERE management_area_id = ?",
            (fallback, area_id),
        )
        conn.execute("DELETE FROM management_areas WHERE id = ?", (area_id,))


# --- thematics --------------------------------------------------------------------------------


def list_thematics(area_id: int) -> list[Thematic]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM thematics WHERE management_area_id = ? ORDER BY position, id", (area_id,)
        ).fetchall()
    return [_thematic_from_row(row) for row in rows]


def get_thematic(area_id: int, slug: str) -> Thematic:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM thematics WHERE management_area_id = ? AND slug = ?", (area_id, slug)
        ).fetchone()
    if row is None:
        raise ThematicNotFoundError(slug)
    return _thematic_from_row(row)


def get_thematic_by_id(thematic_id: int) -> Thematic:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM thematics WHERE id = ?", (thematic_id,)).fetchone()
    if row is None:
        raise ThematicNotFoundError(str(thematic_id))
    return _thematic_from_row(row)


def create_thematic(area_id: int, name: str, description: str = "", *, created_by: int) -> Thematic:
    name = name.strip()
    if not name:
        raise ValueError("le nom de la thématique est obligatoire")
    with get_conn() as conn:
        base = _slugify(name, "thematique")
        slug, suffix = base, 2
        while conn.execute(
            "SELECT 1 FROM thematics WHERE management_area_id = ? AND slug = ?", (area_id, slug)
        ).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM thematics WHERE management_area_id = ?", (area_id,)
        ).fetchone()["p"]
        cursor = conn.execute(
            "INSERT INTO thematics (management_area_id, slug, name, description, position, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (area_id, slug, name, description.strip(), position, created_by),
        )
        return Thematic(cursor.lastrowid, area_id, slug, name, description.strip(), position)


def update_thematic(thematic_id: int, *, name: str, description: str) -> Thematic:
    name = name.strip()
    if not name:
        raise ValueError("le nom de la thématique est obligatoire")
    with get_conn() as conn:
        conn.execute(
            "UPDATE thematics SET name = ?, description = ? WHERE id = ?", (name, description.strip(), thematic_id)
        )
    return get_thematic_by_id(thematic_id)


def delete_thematic(thematic_id: int) -> None:
    """Its µprojets stay in the project, just without a thématique."""
    with get_conn() as conn:
        conn.execute("UPDATE microprojects SET thematic_id = NULL WHERE thematic_id = ?", (thematic_id,))
        conn.execute("DELETE FROM thematics WHERE id = ?", (thematic_id,))


# --- objectives -------------------------------------------------------------------------------


def list_objectives(area_id: int) -> list[Objective]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM area_objectives WHERE management_area_id = ? ORDER BY position, id", (area_id,)
        ).fetchall()
    return [_objective_from_row(row) for row in rows]


def _objective_row(conn: sqlite3.Connection, area_id: int, objective_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM area_objectives WHERE id = ? AND management_area_id = ?", (objective_id, area_id)
    ).fetchone()
    if row is None:
        raise ObjectiveNotFoundError(str(objective_id))
    return row


def create_objective(area_id: int, title: str, detail: str = "", target: str = "", *, created_by: int) -> Objective:
    """Appended last (least important); :func:`reorder_objectives` moves it up."""
    title = title.strip()
    if not title:
        raise ValueError("l'intitulé de l'objectif est obligatoire")
    with get_conn() as conn:
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM area_objectives WHERE management_area_id = ?", (area_id,)
        ).fetchone()["p"]
        cursor = conn.execute(
            "INSERT INTO area_objectives (management_area_id, title, detail, target, position, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (area_id, title, detail.strip(), target.strip(), position, created_by),
        )
        return Objective(cursor.lastrowid, area_id, title, detail.strip(), target.strip(), position)


def update_objective(area_id: int, objective_id: int, *, title: str, detail: str, target: str) -> Objective:
    title = title.strip()
    if not title:
        raise ValueError("l'intitulé de l'objectif est obligatoire")
    with get_conn() as conn:
        _objective_row(conn, area_id, objective_id)
        conn.execute(
            "UPDATE area_objectives SET title = ?, detail = ?, target = ? WHERE id = ?",
            (title, detail.strip(), target.strip(), objective_id),
        )
        return _objective_from_row(_objective_row(conn, area_id, objective_id))


def delete_objective(area_id: int, objective_id: int) -> None:
    with get_conn() as conn:
        _objective_row(conn, area_id, objective_id)
        conn.execute("DELETE FROM area_objectives WHERE id = ?", (objective_id,))


def reorder_objectives(area_id: int, ordered_ids: list[int]) -> list[Objective]:
    """``ordered_ids`` is the new ranking, most important first; it must list exactly this
    project's objectives, each once."""
    with get_conn() as conn:
        existing = {
            row["id"] for row in conn.execute("SELECT id FROM area_objectives WHERE management_area_id = ?", (area_id,))
        }
        if len(ordered_ids) != len(existing) or set(ordered_ids) != existing:
            raise ValueError("l'ordre doit lister exactement les objectifs du projet")
        for position, objective_id in enumerate(ordered_ids):
            conn.execute("UPDATE area_objectives SET position = ? WHERE id = ?", (position, objective_id))
    return list_objectives(area_id)
