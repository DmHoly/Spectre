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

import re
import sqlite3
import unicodedata
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
    code_prefix: str = ""  # « Nat » -> its µprojets are Nat_0001, Nat_0002... ('' = not numbered)


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
    position: int  # orders objectives without a weight (0 = most important)
    weight: float | None = None  # a figure (0-100 %) used for the team's bonus - recorded, shown, ranked by; nothing computed from it
    achieved: bool = False
    validated_by: int | None = None  # id of the µprojet that validated it


def _from_row(row: sqlite3.Row) -> ManagementArea:
    return ManagementArea(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        strategy=row["strategy"],
        created_by=row["created_by"],
        objectives_period=row["objectives_period"],
        code_prefix=row["code_prefix"],
    )


def _thematic_from_row(row: sqlite3.Row) -> Thematic:
    return Thematic(row["id"], row["management_area_id"], row["slug"], row["name"], row["description"], row["position"])


def _objective_from_row(row: sqlite3.Row) -> Objective:
    return Objective(
        row["id"],
        row["management_area_id"],
        row["title"],
        row["detail"],
        row["target"],
        row["position"],
        row["weight"],
        bool(row["achieved"]),
        row["validated_by_microproject_id"],
    )


def _check_weight(weight: float | None) -> float | None:
    if weight is None:
        return None
    if not 0 <= weight <= 100:
        raise ValueError("le pourcentage doit être compris entre 0 et 100 %")
    return round(float(weight), 2)


def _check_validated_by(conn: sqlite3.Connection, microproject_id: int | None) -> int | None:
    if microproject_id is None:
        return None
    if conn.execute("SELECT 1 FROM microprojects WHERE id = ?", (microproject_id,)).fetchone() is None:
        raise ValueError("µprojet validant introuvable")
    return microproject_id


_PREFIX_RE = re.compile(r"[A-Za-z]{2,5}")


def derive_code_prefix(name: str, taken: set[str]) -> str:
    """A code prefix from a project's name - its first letters, « Native » -> « Nat » - longer (or
    numbered) until it's not in ``taken`` (lower-cased prefixes already in use)."""
    letters = re.sub(r"[^A-Za-z]", "", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")) or "Prj"
    base = (letters[0].upper() + letters[1:].lower()) if len(letters) > 1 else (letters.upper() + "x")
    for length in (3, 4, 5):
        candidate = base[:length]
        if len(candidate) >= 2 and candidate.lower() not in taken:
            return candidate
    for letter in "abcdefghijklmnopqrstuvwxyz":
        candidate = base[:4] + letter
        if candidate.lower() not in taken:
            return candidate
    return base[:5]


def _check_prefix(conn: sqlite3.Connection, prefix: str, area_id: int | None) -> str:
    prefix = prefix.strip()
    if not _PREFIX_RE.fullmatch(prefix):
        raise ValueError("le préfixe des numéros de µprojet doit faire 2 à 5 lettres (ex : Nat)")
    clash = conn.execute(
        "SELECT name FROM management_areas WHERE lower(code_prefix) = lower(?) AND id != ?", (prefix, area_id or -1)
    ).fetchone()
    if clash:
        raise ValueError(f"le préfixe « {prefix} » est déjà celui du projet « {clash['name']} »")
    return prefix


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


def create(
    name: str, description: str = "", strategy: str = "", *, created_by: int, code_prefix: str | None = None
) -> ManagementArea:
    """``code_prefix`` numbers its µprojets (« Nat » -> Nat_0001...); derived from the name when omitted."""
    name = name.strip()
    if not name:
        raise ValueError("le nom du projet est obligatoire")
    with get_conn() as conn:
        if code_prefix:
            prefix = _check_prefix(conn, code_prefix, None)
        else:
            taken = {r["code_prefix"].lower() for r in conn.execute("SELECT code_prefix FROM management_areas") if r["code_prefix"]}
            prefix = derive_code_prefix(name, taken)
        slug = _unique_slug(conn, _slugify(name))
        conn.execute(
            "INSERT INTO management_areas (slug, name, description, strategy, created_by, code_prefix) VALUES (?, ?, ?, ?, ?, ?)",
            (slug, name, description.strip(), strategy.strip(), created_by, prefix),
        )
    return get_by_slug(slug)


def update(
    area_id: int,
    *,
    name: str,
    description: str,
    strategy: str,
    objectives_period: str | None = None,
    code_prefix: str | None = None,
) -> ManagementArea:
    """A new ``code_prefix`` only applies to µprojets numbered from now on - existing numbers never change."""
    name = name.strip()
    if not name:
        raise ValueError("le nom du projet est obligatoire")
    with get_conn() as conn:
        row = conn.execute("SELECT slug FROM management_areas WHERE id = ?", (area_id,)).fetchone()
        if row is None:
            raise ManagementAreaNotFoundError(str(area_id))
        conn.execute(
            "UPDATE management_areas SET name = ?, description = ?, strategy = ? WHERE id = ?",
            (name, description.strip(), strategy.strip(), area_id),
        )
        if code_prefix is not None and row["slug"] != UNCLASSIFIED_AREA_SLUG:
            conn.execute(
                "UPDATE management_areas SET code_prefix = ? WHERE id = ?", (_check_prefix(conn, code_prefix, area_id), area_id)
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
    """Heaviest share of the effort first; objectives without a weight after, in their own order."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM area_objectives WHERE management_area_id = ? "
            "ORDER BY weight IS NULL, weight DESC, position, id",
            (area_id,),
        ).fetchall()
    return [_objective_from_row(row) for row in rows]


def _objective_row(conn: sqlite3.Connection, area_id: int, objective_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM area_objectives WHERE id = ? AND management_area_id = ?", (objective_id, area_id)
    ).fetchone()
    if row is None:
        raise ObjectiveNotFoundError(str(objective_id))
    return row


def create_objective(
    area_id: int,
    title: str,
    detail: str = "",
    target: str = "",
    *,
    weight: float | None = None,
    achieved: bool = False,
    validated_by: int | None = None,
    created_by: int,
) -> Objective:
    """Ranked by ``weight`` (the bonus figure); without one, appended last among the unweighted
    objectives - :func:`reorder_objectives` orders those."""
    title = title.strip()
    if not title:
        raise ValueError("l'intitulé de l'objectif est obligatoire")
    weight = _check_weight(weight)
    with get_conn() as conn:
        validated_by = _check_validated_by(conn, validated_by)
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM area_objectives WHERE management_area_id = ?", (area_id,)
        ).fetchone()["p"]
        cursor = conn.execute(
            "INSERT INTO area_objectives (management_area_id, title, detail, target, weight, achieved, "
            "validated_by_microproject_id, position, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (area_id, title, detail.strip(), target.strip(), weight, int(achieved), validated_by, position, created_by),
        )
        return _objective_from_row(_objective_row(conn, area_id, cursor.lastrowid))


def update_objective(
    area_id: int,
    objective_id: int,
    *,
    title: str,
    detail: str,
    target: str,
    weight: float | None = None,
    achieved: bool = False,
    validated_by: int | None = None,
) -> Objective:
    title = title.strip()
    if not title:
        raise ValueError("l'intitulé de l'objectif est obligatoire")
    weight = _check_weight(weight)
    with get_conn() as conn:
        _objective_row(conn, area_id, objective_id)
        validated_by = _check_validated_by(conn, validated_by)
        conn.execute(
            "UPDATE area_objectives SET title = ?, detail = ?, target = ?, weight = ?, achieved = ?, "
            "validated_by_microproject_id = ? WHERE id = ?",
            (title, detail.strip(), target.strip(), weight, int(achieved), validated_by, objective_id),
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
