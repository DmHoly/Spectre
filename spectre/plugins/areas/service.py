"""The corporate strategy layer, a three-level hierarchy:

- **management areas** - the *projets corporate* leadership steers by (Native (PT2), VLC
  (microlink), Nova (PT1)), each with a ranked list of objectives for the coming period;
- **thematics** - the technical thématiques of one project (dopage PGaN, double EBL...);
- **µprojets** (:mod:`spectre.plugins.microprojects.service`) - chains of experiments, attached to
  an area and optionally to one of its thematics.

Thin data-access over the ``management_areas`` / ``thematics`` / ``area_objectives`` tables - like
:mod:`spectre.plugins.microprojects.service` but simpler: none of these has a Follow repo or on-disk home of
its own, and reading is company-wide (every signed-in user sees everything).

Who writes: one rule, :func:`can_manage` - an admin (``users.is_admin``), or a manager of the team
the area is attached to (``management_areas.team_id``, plugin teams). It covers the area, its
thématiques and its objectives; the µprojets of the area follow from it
(:func:`spectre.plugins.microprojects.service.access`). Creating an area: an admin, or a manager
who attaches it to one of the teams they manage (:func:`check_can_create`); changing an area's team
is the admin's alone. A fresh or migrated area has no team: only an admin manages it.

« Non classé » is the **system** area (:attr:`ManagementArea.is_system`): it holds the µprojets not
sorted yet, so it can't be deleted, numbers nothing and takes neither thématique nor objective.

The ``microprojects`` table belongs to the plugin above this one: only the SQL below touches it -
to send the µprojets of a deleted area or thématique back where they belong, and to name the µprojet
that validated an objective.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from ..teams import service as teams
from ..teams.service import Team

DEFAULT_OBJECTIVES_PERIOD = "6 prochains mois"
DEFAULT_HORIZON_MONTHS = 6
UNCLASSIFIED_AREA_SLUG = "non-classe"


class ManagementAreaNotFoundError(NotFound):
    pass


class ThematicNotFoundError(NotFound):
    pass


class ObjectiveNotFoundError(NotFound):
    pass


# « 6 prochains mois », « 12 mois », « 3 derniers mois » -> the number of months
_HORIZON_RE = re.compile(r"(\d+)\s*(?:derniers?\s+|prochains?\s+)?mois", re.IGNORECASE)


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
    team_id: int | None = None  # the team that owns it (plugin teams); None: only an admin manages it

    @property
    def is_system(self) -> bool:
        """« Non classé »: where µprojets wait to be sorted - see the module docstring."""
        return self.slug == UNCLASSIFIED_AREA_SLUG

    @property
    def horizon_months(self) -> int:
        """How far the objectives look ahead, in months (1 to 24), read from ``objectives_period``
        (« 6 prochains mois » -> 6); 6 when the period names no month count (« S1 2027 »)."""
        match = _HORIZON_RE.search(self.objectives_period or "")
        return min(24, max(1, int(match.group(1)))) if match else DEFAULT_HORIZON_MONTHS


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
    validated_by: dict | None = None  # the µprojet that validated it: {"slug", "code", "name"}


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
        team_id=row["team_id"] if "team_id" in row.keys() else None,
    )


def _thematic_from_row(row: sqlite3.Row) -> Thematic:
    return Thematic(row["id"], row["management_area_id"], row["slug"], row["name"], row["description"], row["position"])


# An objective with the µprojet that validated it, numbered the way the microprojects plugin numbers
# them (« Nat_0004 », see spectre.plugins.microprojects.service.format_code).
_OBJECTIVE_SELECT = (
    "SELECT area_objectives.*, microprojects.slug AS validator_slug, microprojects.name AS validator_name, "
    "CASE WHEN microprojects.code_number IS NOT NULL AND microprojects.code_prefix != '' "
    "THEN printf('%s_%04d', microprojects.code_prefix, microprojects.code_number) END AS validator_code "
    "FROM area_objectives LEFT JOIN microprojects ON microprojects.id = area_objectives.validated_by_microproject_id"
)


def _objective_from_row(row: sqlite3.Row) -> Objective:
    validator = (
        {"slug": row["validator_slug"], "code": row["validator_code"], "name": row["validator_name"]}
        if row["validator_slug"]
        else None
    )
    return Objective(
        row["id"],
        row["management_area_id"],
        row["title"],
        row["detail"],
        row["target"],
        row["position"],
        row["weight"],
        bool(row["achieved"]),
        validator,
    )


def _check_weight(weight: float | None) -> float | None:
    if weight is None:
        return None
    if not 0 <= weight <= 100:
        raise InvalidInput("le pourcentage doit être compris entre 0 et 100 %")
    return round(float(weight), 2)


def _validator_id(conn: sqlite3.Connection, microproject_slug: str | None) -> int | None:
    if not microproject_slug:
        return None
    row = conn.execute("SELECT id FROM microprojects WHERE slug = ?", (microproject_slug,)).fetchone()
    if row is None:
        raise InvalidInput(f"µprojet validant {microproject_slug!r} introuvable")
    return row["id"]


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
        raise InvalidInput("le préfixe des numéros de µprojet doit faire 2 à 5 lettres (ex : Nat)")
    clash = conn.execute(
        "SELECT name FROM management_areas WHERE lower(code_prefix) = lower(?) AND id != ?", (prefix, area_id or -1)
    ).fetchone()
    if clash:
        raise Conflict(f"le préfixe « {prefix} » est déjà celui du projet « {clash['name']} »")
    return prefix


def _required(value: str, message: str) -> str:
    value = value.strip()
    if not value:
        raise InvalidInput(message)
    return value


def slugify(name: str) -> str:
    """A URL-safe slug from a display name: strip diacritics ("Fiabilité" -> "fiabilite"), then
    collapse anything non-alphanumeric to single dashes. Shared with
    :mod:`spectre.plugins.microprojects.service`.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")


def _slugify(name: str, fallback: str = "projet") -> str:
    return slugify(name) or fallback


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug, suffix = base, 2
    while conn.execute("SELECT 1 FROM management_areas WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def list_all(*, team_id: int | None = None) -> list[ManagementArea]:
    """Every area - of one team with ``team_id``."""
    # « Non classé » always last; the rest in creation order (the flagship projects keep the order
    # they were seeded in, a later hand-created one lands after them).
    where, params = ("WHERE team_id = ? ", [team_id]) if team_id is not None else ("", [])
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM management_areas {where}ORDER BY (slug = ?), id", [*params, UNCLASSIFIED_AREA_SLUG]
        ).fetchall()
    return [_from_row(row) for row in rows]


# --- droits -----------------------------------------------------------------------------------


def managed_area_ids(user: User) -> set[int]:
    """The areas ``user`` manages as a manager of their team - not counting the admin's rights,
    which :func:`can_manage` adds."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT management_areas.id FROM management_areas "
            "JOIN team_members ON team_members.team_id = management_areas.team_id "
            "WHERE team_members.user_id = ? AND team_members.role = 'manager'",
            (user.id,),
        ).fetchall()
    return {row["id"] for row in rows}


def can_manage(user: User, area: ManagementArea) -> bool:
    """The one rule for writing an area, its thématiques and its objectives: an admin, or a
    manager of the area's team."""
    return user.is_admin or (area.team_id is not None and area.team_id in teams.managed_team_ids(user.id))


def require_manage(user: User, area: ManagementArea) -> None:
    if not can_manage(user, area):
        raise Forbidden("seuls un administrateur ou un manager de l'équipe de ce projet peuvent le modifier")


def check_can_create(user: User, team: Team | None) -> None:
    """A new area: an admin (with or without a team), or a manager attaching it to one of the
    teams they manage."""
    if user.is_admin:
        return
    if team is None or not teams.can_manage(user, team):
        raise Forbidden("un manager crée un projet en le rattachant à l'une de ses équipes ; sinon, c'est à un administrateur")


def team_of(slug: str | None) -> Team | None:
    """The team a request body names (``None``: no team) - unknown, it is an invalid input."""
    if not slug:
        return None
    try:
        return teams.get_by_slug(slug)
    except teams.TeamNotFoundError as exc:
        raise InvalidInput(f"équipe {slug!r} introuvable", code="unknown_team") from exc


def get_by_slug(slug: str) -> ManagementArea:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM management_areas WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise ManagementAreaNotFoundError(f"projet {slug!r} introuvable")
    return _from_row(row)


def get_by_id(area_id: int) -> ManagementArea:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM management_areas WHERE id = ?", (area_id,)).fetchone()
    if row is None:
        raise ManagementAreaNotFoundError(f"projet n° {area_id} introuvable")
    return _from_row(row)


def create(
    name: str,
    description: str = "",
    strategy: str = "",
    *,
    created_by: int,
    code_prefix: str | None = None,
    team_id: int | None = None,
) -> ManagementArea:
    """``code_prefix`` numbers its µprojets (« Nat » -> Nat_0001...); derived from the name when
    omitted. ``team_id``: the team that owns it (the caller checks the right to attach it,
    :func:`check_can_create`)."""
    name = _required(name, "le nom du projet est obligatoire")
    with get_conn() as conn:
        if code_prefix:
            prefix = _check_prefix(conn, code_prefix, None)
        else:
            taken = {r["code_prefix"].lower() for r in conn.execute("SELECT code_prefix FROM management_areas") if r["code_prefix"]}
            prefix = derive_code_prefix(name, taken)
        slug = _unique_slug(conn, _slugify(name))
        conn.execute(
            "INSERT INTO management_areas (slug, name, description, strategy, created_by, code_prefix, team_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (slug, name, description.strip(), strategy.strip(), created_by, prefix, team_id),
        )
    return get_by_slug(slug)


def update(area: ManagementArea, **changes: str | None) -> ManagementArea:
    """Only the fields given change (``name``, ``description``, ``strategy``, ``objectives_period``,
    ``code_prefix``). A new ``code_prefix`` only applies to µprojets numbered from now on - existing
    numbers never change; the system area numbers nothing."""
    columns: dict[str, str] = {}
    if changes.get("name") is not None:
        columns["name"] = _required(changes["name"], "le nom du projet est obligatoire")
    for key in ("description", "strategy"):
        if changes.get(key) is not None:
            columns[key] = changes[key].strip()
    if changes.get("objectives_period") is not None:
        columns["objectives_period"] = changes["objectives_period"].strip() or DEFAULT_OBJECTIVES_PERIOD
    with get_conn() as conn:
        if changes.get("code_prefix") is not None:
            if area.is_system:
                raise Conflict(f"« {area.name} » ne numérote pas ses µprojets : il n'a pas de préfixe")
            columns["code_prefix"] = _check_prefix(conn, changes["code_prefix"], area.id)
        if columns:
            assignments = ", ".join(f"{column} = ?" for column in columns)
            conn.execute(f"UPDATE management_areas SET {assignments} WHERE id = ?", (*columns.values(), area.id))
    return get_by_id(area.id)


def set_team(user: User, area: ManagementArea, team: Team | None) -> ManagementArea:
    """Attach the area to ``team`` (``None``: to no team) - an admin only (403 otherwise); the
    system area stays without one (409)."""
    if not user.is_admin:
        raise Forbidden("seul un administrateur rattache un projet à une équipe")
    team_id = team.id if team else None
    if team_id == area.team_id:
        return area
    if area.is_system:
        raise Conflict(f"« {area.name} » n'appartient à aucune équipe : ses µprojets n'ont que leurs membres et l'administrateur")
    with get_conn() as conn:
        conn.execute("UPDATE management_areas SET team_id = ? WHERE id = ?", (team_id, area.id))
    return get_by_id(area.id)


def delete(area: ManagementArea) -> None:
    """Remove an area; its µprojets fall back to the system area (without thématique) rather than
    being deleted, its thématiques and objectives go with it. The system area itself stays."""
    if area.is_system:
        raise Conflict(f"« {area.name} » ne peut pas être supprimé")
    with get_conn() as conn:
        fallback = conn.execute("SELECT id FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)).fetchone()["id"]
        conn.execute(
            "UPDATE microprojects SET management_area_id = ?, thematic_id = NULL WHERE management_area_id = ?",
            (fallback, area.id),
        )
        conn.execute("DELETE FROM management_areas WHERE id = ?", (area.id,))


def _refuse_on_system_area(area: ManagementArea, what: str) -> None:
    if area.is_system:
        raise Conflict(f"« {area.name} » ne porte pas de {what} : rattachez d'abord ses µprojets à un projet")


# --- thematics --------------------------------------------------------------------------------


def list_thematics(area_id: int | None = None) -> list[Thematic]:
    """The thématiques of one area, or of every area (``None``) - area by area, each in its order."""
    with get_conn() as conn:
        if area_id is None:
            rows = conn.execute("SELECT * FROM thematics ORDER BY management_area_id, position, id").fetchall()
        else:
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
        raise ThematicNotFoundError(f"thématique {slug!r} introuvable")
    return _thematic_from_row(row)


def get_thematic_by_id(thematic_id: int) -> Thematic:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM thematics WHERE id = ?", (thematic_id,)).fetchone()
    if row is None:
        raise ThematicNotFoundError(f"thématique n° {thematic_id} introuvable")
    return _thematic_from_row(row)


def create_thematic(area: ManagementArea, name: str, description: str = "", *, created_by: int) -> Thematic:
    _refuse_on_system_area(area, "thématique")
    name = _required(name, "le nom de la thématique est obligatoire")
    with get_conn() as conn:
        base = _slugify(name, "thematique")
        slug, suffix = base, 2
        while conn.execute(
            "SELECT 1 FROM thematics WHERE management_area_id = ? AND slug = ?", (area.id, slug)
        ).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM thematics WHERE management_area_id = ?", (area.id,)
        ).fetchone()["p"]
        cursor = conn.execute(
            "INSERT INTO thematics (management_area_id, slug, name, description, position, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (area.id, slug, name, description.strip(), position, created_by),
        )
        return Thematic(cursor.lastrowid, area.id, slug, name, description.strip(), position)


def update_thematic(thematic: Thematic, *, name: str | None = None, description: str | None = None) -> Thematic:
    """Only the fields given change; the slug stays (links to the thématique keep working)."""
    columns: dict[str, str] = {}
    if name is not None:
        columns["name"] = _required(name, "le nom de la thématique est obligatoire")
    if description is not None:
        columns["description"] = description.strip()
    if columns:
        assignments = ", ".join(f"{column} = ?" for column in columns)
        with get_conn() as conn:
            conn.execute(f"UPDATE thematics SET {assignments} WHERE id = ?", (*columns.values(), thematic.id))
    return get_thematic_by_id(thematic.id)


def delete_thematic(thematic: Thematic) -> None:
    """Its µprojets stay in the project, just without a thématique."""
    with get_conn() as conn:
        conn.execute("UPDATE microprojects SET thematic_id = NULL WHERE thematic_id = ?", (thematic.id,))
        conn.execute("DELETE FROM thematics WHERE id = ?", (thematic.id,))


# --- objectives -------------------------------------------------------------------------------


def list_objectives(area_id: int) -> list[Objective]:
    """Heaviest share of the effort first; objectives without a weight after, in creation order."""
    with get_conn() as conn:
        rows = conn.execute(
            f"{_OBJECTIVE_SELECT} WHERE area_objectives.management_area_id = ? "
            "ORDER BY area_objectives.weight IS NULL, area_objectives.weight DESC, area_objectives.position, area_objectives.id",
            (area_id,),
        ).fetchall()
    return [_objective_from_row(row) for row in rows]


def _objective(conn: sqlite3.Connection, area_id: int, objective_id: int) -> Objective:
    row = conn.execute(
        f"{_OBJECTIVE_SELECT} WHERE area_objectives.id = ? AND area_objectives.management_area_id = ?", (objective_id, area_id)
    ).fetchone()
    if row is None:
        raise ObjectiveNotFoundError(f"objectif n° {objective_id} introuvable")
    return _objective_from_row(row)


def get_objective(area: ManagementArea, objective_id: int) -> Objective:
    with get_conn() as conn:
        return _objective(conn, area.id, objective_id)


def create_objective(
    area: ManagementArea,
    title: str,
    detail: str = "",
    target: str = "",
    *,
    weight: float | None = None,
    achieved: bool = False,
    validated_by: str | None = None,
    created_by: int,
) -> Objective:
    """Ranked by ``weight`` (the bonus figure); without one, after the weighted objectives, in
    creation order. ``validated_by`` is the slug of the µprojet that validated it."""
    _refuse_on_system_area(area, "objectif")
    title = _required(title, "l'intitulé de l'objectif est obligatoire")
    weight = _check_weight(weight)
    with get_conn() as conn:
        validator_id = _validator_id(conn, validated_by)
        position = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM area_objectives WHERE management_area_id = ?", (area.id,)
        ).fetchone()["p"]
        cursor = conn.execute(
            "INSERT INTO area_objectives (management_area_id, title, detail, target, weight, achieved, "
            "validated_by_microproject_id, position, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (area.id, title, detail.strip(), target.strip(), weight, int(achieved), validator_id, position, created_by),
        )
        return _objective(conn, area.id, cursor.lastrowid)


def update_objective(area: ManagementArea, objective_id: int, **changes) -> Objective:
    """Only the fields given change (``title``, ``detail``, ``target``, ``weight``, ``achieved``,
    ``validated_by``); ``weight`` and ``validated_by`` may be set back to ``None``."""
    columns: dict[str, object] = {}
    if changes.get("title") is not None:
        columns["title"] = _required(changes["title"], "l'intitulé de l'objectif est obligatoire")
    for key in ("detail", "target"):
        if changes.get(key) is not None:
            columns[key] = changes[key].strip()
    if "weight" in changes:
        columns["weight"] = _check_weight(changes["weight"])
    if changes.get("achieved") is not None:
        columns["achieved"] = int(changes["achieved"])
    with get_conn() as conn:
        _objective(conn, area.id, objective_id)
        if "validated_by" in changes:
            columns["validated_by_microproject_id"] = _validator_id(conn, changes["validated_by"])
        if columns:
            assignments = ", ".join(f"{column} = ?" for column in columns)
            conn.execute(f"UPDATE area_objectives SET {assignments} WHERE id = ?", (*columns.values(), objective_id))
        return _objective(conn, area.id, objective_id)


def delete_objective(area: ManagementArea, objective_id: int) -> None:
    with get_conn() as conn:
        _objective(conn, area.id, objective_id)
        conn.execute("DELETE FROM area_objectives WHERE id = ?", (objective_id,))
