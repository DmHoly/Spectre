"""Microprojects and membership - the data-access layer over the ``microprojects``/``memberships``/
``invitations`` tables, plus each microproject's own directory on disk (:func:`microproject_dir`),
under which the other plugins keep its Follow repository, saved structures, step presets and
attachments. Follow and StructureForge never know a "microproject" exists; the plugins map a slug to
the paths they're given from here.

A µprojet belongs to one team (``microprojects.team_id``): that of its thématique, otherwise one of the
teams that work in its corporate project (:func:`resolve_team`); none for the µprojets that predate the
teams and those of « Non classé ».

Who may do what in a µprojet is one rule, :func:`access` (and :func:`effective_role`,
:func:`has_role`, :func:`accesses` for a list): the ``owner`` role for an admin and for a manager of
the µprojet's team, otherwise the role its membership gives; without one, the ``viewer`` role for
whoever the thématique shows it to - a member of its team, of a team invited into the thématique, or of
another µprojet of the thématique (an account invited into a µprojet reads the thématique's other
µprojets, never writes them). Every plugin checks a µprojet role through these functions -
:func:`role_for` and :func:`list_for_user` only read the ``memberships`` table. :func:`visible` tells
which µprojets a lookup may name at all: those with a role, and the open ones (no team, in a thématique
the caller sees).

Membership keeps two invariants, whatever the route: a µprojet always has at least one owner, and
its creator stays an owner (:func:`change_member_role`, :func:`remove_member`). An invitation is
stored by the SHA-256 of its token only: the token in clear leaves :func:`create_invitation` for the
e-mail and is never read back.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ...kernel.db import data_dir, get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ...kernel.locks import keyed_lock
from ..accounts import security
from ..accounts import service as accounts
from ..areas import service as areas
from ..areas.service import UNCLASSIFIED_AREA_SLUG, slugify
from ..teams import service as teams

ROLE_ORDER = {"viewer": 0, "editor": 1, "owner": 2}
# Slugs a µprojet never gets, so that a page under /microprojets/<literal> stays possible.
RESERVED_SLUGS = frozenset({"new", "nouvelle"})


class MicroprojectNotFoundError(NotFound):
    pass


@dataclass(frozen=True)
class Microproject:
    """A "µprojet": one topic addressed under a management area (:mod:`spectre.plugins.areas.service`).
    Table/dir/API keep the historical name ``microproject``.
    """

    id: int
    slug: str
    name: str
    description: str
    created_by: int
    management_area_id: int | None = None
    thematic_id: int | None = None  # one of that area's thématiques (spectre.plugins.areas.service.Thematic), optional
    code: str | None = None  # « Nat_0004 » - see assign_code ; None while it sits in « Non classé »
    created_at: str | None = None  # SQLite « YYYY-MM-DD HH:MM:SS », UTC
    team_id: int | None = None  # the team it belongs to (plugin teams); None: no team, see the module docstring


@dataclass(frozen=True)
class Invitation:
    """A pending invitation - without its token, which only the e-mail carries."""

    id: int
    microproject_id: int
    email: str
    role: str
    invited_by: int
    created_at: str
    expires_at: str


def format_code(prefix: str, number: int) -> str:
    return f"{prefix}_{number:04d}"


def _microproject_from_row(row: sqlite3.Row) -> Microproject:
    keys = row.keys()
    code = (
        format_code(row["code_prefix"], row["code_number"])
        if "code_number" in keys and row["code_number"] is not None and row["code_prefix"]
        else None
    )
    return Microproject(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        created_by=row["created_by"],
        management_area_id=row["management_area_id"] if "management_area_id" in keys else None,
        thematic_id=row["thematic_id"] if "thematic_id" in keys else None,
        code=code,
        created_at=row["created_at"] if "created_at" in keys else None,
        team_id=row["team_id"] if "team_id" in keys else None,
    )


def assign_code(conn: sqlite3.Connection, microproject_id: int, management_area_id: int | None) -> None:
    """Give a µprojet its number - its corporate project's prefix and the next free number for that
    prefix (Nat_0001, Nat_0002...) - if it has none yet and the project numbers its µprojets. A
    number is never changed afterwards, even if the µprojet moves to another project: « regarde
    Nat_0004 » must always point to the same µprojet."""
    row = conn.execute("SELECT code_number FROM microprojects WHERE id = ?", (microproject_id,)).fetchone()
    if row is None or row["code_number"] is not None or management_area_id is None:
        return
    area = conn.execute("SELECT code_prefix FROM management_areas WHERE id = ?", (management_area_id,)).fetchone()
    prefix = area["code_prefix"] if area else ""
    if not prefix:
        return
    number = conn.execute(
        "SELECT COALESCE(MAX(code_number), 0) + 1 AS n FROM microprojects WHERE lower(code_prefix) = lower(?)", (prefix,)
    ).fetchone()["n"]
    conn.execute("UPDATE microprojects SET code_prefix = ?, code_number = ? WHERE id = ?", (prefix, number, microproject_id))


_CODE_RE = re.compile(r"^\s*([A-Za-z]{2,5})[\s_\-]*0*(\d{1,6})\s*$")


def _folded(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower().strip()


def search(text: str, *, limit: int = 8) -> list[Microproject]:
    """µprojets matching what someone typed in the search bar: its exact number first (« Nat 4 »),
    then numbers starting with it (« nat » -> every Nat_…), then names starting with / containing
    every word typed - accents and case ignored."""
    query = _folded(text)
    if not query:
        return []
    try:
        exact = get_by_code(text)
    except MicroprojectNotFoundError:
        exact = None
    words = query.split()
    scored = []
    for microproject in list_all():
        if exact and microproject.id == exact.id:
            continue
        code = (microproject.code or "").lower()
        name = _folded(microproject.name)
        if code and code.replace("_", "").startswith(query.replace(" ", "").replace("_", "")):
            rank = 1
        elif name.startswith(query):
            rank = 2
        elif all(word in f"{name} {code}" for word in words):
            rank = 3
        else:
            continue
        scored.append((rank, code or "~", name, microproject))
    scored.sort(key=lambda item: item[:3])
    results = ([exact] if exact else []) + [item[3] for item in scored]
    return results[:limit]


def get_by_code(text: str) -> Microproject:
    """A µprojet by its number, written the way people say it: « Nat_0004 », « Nat 4 », « nat4 »."""
    match = _CODE_RE.match(text or "")
    row = None
    if match:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM microprojects WHERE lower(code_prefix) = lower(?) AND code_number = ?",
                (match.group(1), int(match.group(2))),
            ).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(f"aucun µprojet numéroté « {text} »")
    return _microproject_from_row(row)


def _unique_slug(conn: sqlite3.Connection, name: str) -> str:
    base = slugify(name) or "microprojet"
    slug = base
    suffix = 2
    while slug in RESERVED_SLUGS or conn.execute("SELECT 1 FROM microprojects WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _area(area_slug: str | None) -> areas.ManagementArea:
    if not area_slug:
        raise InvalidInput("un µprojet appartient toujours à un projet")
    try:
        return areas.get_by_slug(area_slug)
    except areas.ManagementAreaNotFoundError as exc:
        raise InvalidInput(f"projet {area_slug!r} introuvable") from exc


def _placement_forbidden(area: areas.ManagementArea) -> Forbidden:
    return Forbidden(
        f"le projet « {area.name} » est celui de ses équipes : seuls leurs membres et un administrateur "
        "peuvent y créer ou y déplacer un µprojet",
        code="placement_forbidden",
    )


def resolve_team(
    user: accounts.User,
    area: areas.ManagementArea,
    thematic: areas.Thematic | None,
    requested: str | None = None,
    current_team_id: int | None = None,
) -> int | None:
    """The team a µprojet placed in ``area`` (and ``thematic``) belongs to, and whether ``user`` may
    place it there - the one check of :func:`create` and :func:`update`.

    In a thématique that has a team, it is that team's (``requested``, when given, must be it - 422
    ``team_mismatch``), and ``user`` must be an admin or one of its members (403
    ``placement_forbidden``). Otherwise it is one of the teams that work in the area - ``requested``
    (a slug), else the µprojet's current team if it still fits, else the only one that fits (several:
    422 ``team_required``) - among those ``user`` belongs to, every one for an admin. In « Non classé »
    and in an area without team it is ``requested`` (an admin, or a member of it) or, failing that, the
    current team: no team for a new µprojet.
    """
    mine = set(teams.roles_of(user.id))
    asked = areas.team_of(requested)
    if thematic is not None and thematic.team_id is not None:
        if asked is not None and asked.id != thematic.team_id:
            raise InvalidInput("la thématique appartient à une autre équipe", code="team_mismatch")
        if not (user.is_admin or thematic.team_id in mine):
            raise _placement_forbidden(area)
        return thematic.team_id
    attached = set(areas.attached_team_ids(area.id))
    if area.is_system or not attached:
        if asked is None:
            return current_team_id
        if not (user.is_admin or asked.id in mine):
            raise _placement_forbidden(area)
        return asked.id
    candidates = attached if user.is_admin else attached & mine
    if asked is not None:
        if asked.id not in attached:
            raise InvalidInput(f"l'équipe « {asked.name} » ne travaille pas dans « {area.name} »", code="team_not_in_area")
        if asked.id not in candidates:
            raise _placement_forbidden(area)
        return asked.id
    if current_team_id in candidates:
        return current_team_id
    if not candidates:
        raise _placement_forbidden(area)
    if len(candidates) > 1:
        raise InvalidInput("plusieurs de vos équipes conviennent : précisez l'équipe du µprojet", code="team_required")
    return next(iter(candidates))


def _thematic_id(area_id: int, thematic_slug: str | None, user: accounts.User) -> int | None:
    """The thématique of that slug in the area - one the caller does not see is unknown to them."""
    if not thematic_slug:
        return None
    try:
        return areas.get_visible_thematic(user, area_id, thematic_slug).id
    except areas.ThematicNotFoundError as exc:
        raise InvalidInput(f"la thématique {thematic_slug!r} n'appartient pas à ce projet") from exc


def create(
    name: str,
    description: str,
    *,
    owner: accounts.User,
    area: str | None = None,
    thematic: str | None = None,
    team: str | None = None,
) -> Microproject:
    """A new µprojet, its creator (``owner``) its first owner. ``area`` (a project's slug, « Non
    classé » by default) and ``thematic`` (one of that project's thématiques) say where it sits, and
    ``team`` (a slug) whose it is - a place ``owner`` may put a µprojet in, and a team that goes with
    it (:func:`resolve_team`, 403 otherwise)."""
    name = name.strip()
    if not name:
        raise InvalidInput("le nom du µprojet est obligatoire")
    target = _area(area or UNCLASSIFIED_AREA_SLUG)
    area_id, owner_id = target.id, owner.id
    thematic_id = _thematic_id(area_id, thematic, owner)
    team_id = resolve_team(owner, target, areas.get_thematic_by_id(thematic_id) if thematic_id else None, team)
    with get_conn() as conn:
        slug = _unique_slug(conn, name)
        cursor = conn.execute(
            "INSERT INTO microprojects (slug, name, description, management_area_id, thematic_id, created_by, team_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (slug, name, description.strip(), area_id, thematic_id, owner_id, team_id),
        )
        microproject_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, 'owner')",
            (microproject_id, owner_id),
        )
        assign_code(conn, microproject_id, area_id)
    microproject_dir(slug)  # create the on-disk home for this microproject's Follow repo/structures upfront
    return get_by_id(microproject_id)


def set_management_area(
    microproject_id: int, management_area_id: int, thematic_id: int | None = None, team_id: int | None = None
) -> None:
    """Move a µprojet to an area and, optionally, one of its thématiques, and hand it to ``team_id`` -
    the caller checks that ``thematic_id`` belongs to ``management_area_id`` and the team to the place
    (:func:`resolve_team`)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE microprojects SET management_area_id = ?, thematic_id = ?, team_id = ? WHERE id = ?",
            (management_area_id, thematic_id, team_id, microproject_id),
        )
        assign_code(conn, microproject_id, management_area_id)  # numbered on first landing in a numbered project


def update(slug: str, user: accounts.User, changes: dict) -> Microproject:
    """Only the fields given change: ``name``, ``description``, and where the µprojet sits -
    ``area`` (a project's slug; changing project drops its thématique), ``thematic`` (the slug of one
    of that project's thématiques, or ``None``) and ``team`` (a slug: the team it belongs to). The
    ``owner`` role only (:func:`access`: its owners, the managers of its team, the admins); a new place
    or team also needs the right to place a µprojet there (:func:`resolve_team`)."""
    microproject = get_by_slug(slug)
    if not has_role(user, microproject, "owner"):
        raise Forbidden("seuls un propriétaire du µprojet, un manager de son équipe ou un administrateur peuvent le modifier")

    name, description = microproject.name, microproject.description
    if changes.get("name") is not None:
        name = changes["name"].strip()
        if not name:
            raise InvalidInput("le nom du µprojet est obligatoire")
    if changes.get("description") is not None:
        description = changes["description"].strip()
    area_id, thematic_id = microproject.management_area_id, microproject.thematic_id
    target = areas.get_by_id(area_id) if area_id is not None else None
    if "area" in changes:
        target = _area(changes["area"])
        area_id = target.id
        if area_id != microproject.management_area_id:
            thematic_id = None
    if "thematic" in changes:
        thematic_id = _thematic_id(area_id, changes["thematic"], user)

    team_id = microproject.team_id
    if (area_id, thematic_id) != (microproject.management_area_id, microproject.thematic_id) or changes.get("team"):
        thematic = areas.get_thematic_by_id(thematic_id) if thematic_id else None
        team_id = resolve_team(user, target, thematic, changes.get("team"), microproject.team_id)

    with get_conn() as conn:
        conn.execute("UPDATE microprojects SET name = ?, description = ? WHERE id = ?", (name, description, microproject.id))
    if (area_id, thematic_id, team_id) != (microproject.management_area_id, microproject.thematic_id, microproject.team_id):
        set_management_area(microproject.id, area_id, thematic_id, team_id)
    return get_by_id(microproject.id)


def list_by_management_area(management_area_id: int) -> list[Microproject]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM microprojects WHERE management_area_id = ? ORDER BY created_at DESC", (management_area_id,)
        ).fetchall()
    return [_microproject_from_row(row) for row in rows]


def list_all() -> list[Microproject]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM microprojects ORDER BY created_at DESC").fetchall()
    return [_microproject_from_row(row) for row in rows]


def get_by_slug(slug: str) -> Microproject:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microprojects WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(f"µprojet {slug!r} introuvable")
    return _microproject_from_row(row)


def get_by_id(microproject_id: int) -> Microproject:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microprojects WHERE id = ?", (microproject_id,)).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(f"µprojet n° {microproject_id} introuvable")
    return _microproject_from_row(row)


def role_for(microproject_id: int, user_id: int) -> str | None:
    """The role the ``memberships`` table gives - not the policy: see :func:`access`."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject_id, user_id)
        ).fetchone()
    return row["role"] if row else None


# -- droits -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Access:
    """What someone may do in a µprojet: ``role`` (``viewer`` < ``editor`` < ``owner``, ``None``:
    nothing), where it comes from (``source``: ``membership``, ``team_manager``, ``admin``, or, for a
    ``viewer`` the thématique shows it to, ``team``, ``thematic_team`` or ``thematic_guest``) and the
    role their membership alone gives (``membership``)."""

    role: str | None = None
    source: str | None = None
    membership: str | None = None

    def at_least(self, min_role: str) -> bool:
        return self.role is not None and ROLE_ORDER[self.role] >= ROLE_ORDER[min_role]

    @property
    def is_mine(self) -> bool:
        """Among « my µprojets »: a member, a member or manager of its team (an admin is not, by being one)."""
        return self.membership is not None or self.source in ("team_manager", "team")


NO_ACCESS = Access()


class _Standing:
    """What decides a user's access to any µprojet, read once for a whole list: their memberships,
    their teams, and the thématiques their teams or their memberships open to them."""

    def __init__(self, user: accounts.User) -> None:
        self.user = user
        self.memberships = _membership_roles(user.id)
        self.roles = teams.roles_of(user.id)
        self.managed = {team_id for team_id, role in self.roles.items() if role == "manager"}
        self.team_thematics = areas.thematic_ids_of_teams(list(self.roles))
        self.guest_thematics = areas.guest_thematic_ids(user.id)

    def access(self, microproject: Microproject) -> Access:
        """The one rule. An owner by membership stays one; a manager of the µprojet's team, then an
        admin, are owners; then the role of the membership, if any; then the reading the thématique
        gives - a member of the µprojet's team, of a team of its thématique, of another µprojet of it."""
        membership = self.memberships.get(microproject.id)
        if membership == "owner":
            return Access("owner", "membership", membership)
        if microproject.team_id is not None and microproject.team_id in self.managed:
            return Access("owner", "team_manager", membership)
        if self.user.is_admin:
            return Access("owner", "admin", membership)
        if membership is not None:
            return Access(membership, "membership", membership)
        if microproject.team_id is not None and microproject.team_id in self.roles:
            return Access("viewer", "team")
        if microproject.thematic_id in self.team_thematics:
            return Access("viewer", "thematic_team")
        if microproject.thematic_id in self.guest_thematics:
            return Access("viewer", "thematic_guest")
        return NO_ACCESS


def access(user: accounts.User, microproject: Microproject) -> Access:
    return _Standing(user).access(microproject)


def effective_role(user: accounts.User, microproject: Microproject) -> str | None:
    """``owner`` for an admin or a manager of the µprojet's team, otherwise the role of the
    membership or the one the thématique gives, otherwise ``None``."""
    return access(user, microproject).role


def has_role(user: accounts.User, microproject: Microproject, min_role: str) -> bool:
    return access(user, microproject).at_least(min_role)


def check_role(user: accounts.User, microproject: Microproject, min_role: str) -> None:
    """403 unless ``user`` has at least ``min_role`` in ``microproject``."""
    if not has_role(user, microproject, min_role):
        raise Forbidden("vous n'avez pas les droits nécessaires pour cette action")


def _membership_roles(user_id: int) -> dict[int, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT microproject_id, role FROM memberships WHERE user_id = ?", (user_id,)).fetchall()
    return {row["microproject_id"]: row["role"] for row in rows}


def accesses(user: accounts.User, microprojects: Iterable[Microproject]) -> dict[int, Access]:
    """:func:`access` for each µprojet of a list, by id - a few queries for the whole list."""
    standing = _Standing(user)
    return {m.id: standing.access(m) for m in microprojects}


def visible(user: accounts.User, microprojects: Iterable[Microproject]) -> list[Microproject]:
    """The µprojets of a list ``user`` may know exist - what company-wide lookups (search, number,
    the stats of a project) are limited to: those they have a role in, and the open ones - without
    a team, in no thématique or in one they see. The others are another team's."""
    found = list(microprojects)
    standing = _Standing(user)
    seen = areas.visible_thematic_ids(user)
    return [
        m
        for m in found
        if standing.access(m).role is not None
        or (m.team_id is None and (m.thematic_id is None or seen is None or m.thematic_id in seen))
    ]


def list_mine(user: accounts.User) -> list[tuple[Microproject, Access]]:
    """« My µprojets »: those I am a member of, and those of the teams I belong to - newest first."""
    everything = list_all()
    found = accesses(user, everything)
    return [(m, found[m.id]) for m in everything if found[m.id].is_mine]


def list_readable(user: accounts.User) -> list[tuple[Microproject, Access]]:
    """Every µprojet ``user`` has a role in, however it comes to them (their teams, an invitation,
    a thématique's guests) - newest first."""
    everything = list_all()
    found = accesses(user, everything)
    return [(m, found[m.id]) for m in everything if found[m.id].role is not None]


def owners_by_microproject(microproject_ids: list[int]) -> dict[int, list[dict]]:
    """The owners (``{"id", "name"}``) of each µprojet, its creator first when still an owner -
    what the cards and headers show as « Propriétaire »; one query for a whole list."""
    if not microproject_ids:
        return {}
    placeholders = ",".join("?" * len(microproject_ids))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT memberships.microproject_id, users.id, users.name FROM memberships "
            "JOIN users ON users.id = memberships.user_id "
            "JOIN microprojects ON microprojects.id = memberships.microproject_id "
            f"WHERE memberships.role = 'owner' AND memberships.microproject_id IN ({placeholders}) "
            "ORDER BY memberships.microproject_id, users.id != microprojects.created_by, users.name",
            list(microproject_ids),
        ).fetchall()
    owners: dict[int, list[dict]] = {microproject_id: [] for microproject_id in microproject_ids}
    for row in rows:
        owners[row["microproject_id"]].append({"id": row["id"], "name": row["name"]})
    return owners


# -- membres ----------------------------------------------------------------------------------------

_MEMBER_SELECT = (
    "SELECT users.id, users.name, users.email, memberships.role, users.id = microprojects.created_by AS is_creator "
    "FROM memberships JOIN users ON users.id = memberships.user_id "
    "JOIN microprojects ON microprojects.id = memberships.microproject_id "
)


def _member_from_row(row: sqlite3.Row) -> dict:
    return {**dict(row), "is_creator": bool(row["is_creator"])}


def _check_role(role: str) -> None:
    if role not in ROLE_ORDER:
        raise InvalidInput(f"rôle inconnu : {role!r}")


def list_members(microproject_id: int) -> list[dict]:
    """``[{id, name, email, role, is_creator}]``, by name."""
    with get_conn() as conn:
        rows = conn.execute(_MEMBER_SELECT + "WHERE memberships.microproject_id = ? ORDER BY users.name", (microproject_id,)).fetchall()
    return [_member_from_row(row) for row in rows]


def get_member(microproject_id: int, user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            _MEMBER_SELECT + "WHERE memberships.microproject_id = ? AND memberships.user_id = ?", (microproject_id, user_id)
        ).fetchone()
    if row is None:
        raise NotFound("cette personne n'est pas membre du µprojet")
    return _member_from_row(row)


def add_member(microproject: Microproject, email: str, role: str) -> dict:
    """Add the account of ``email`` to the µprojet - 404 ``no_account`` if there is none (invite
    it instead: :func:`create_invitation`), 409 if it is already a member. Its pending invitations
    to this µprojet are dropped: they have nothing left to give."""
    _check_role(role)
    user = accounts.get_by_email(email)
    if user is None:
        raise NotFound(f"aucun compte n'existe pour {accounts.normalize_email(email)!r} : invitez cette personne", code="no_account")
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?)", (microproject.id, user.id, role)
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"{user.email} est déjà membre du µprojet", code="already_member") from exc
        conn.execute("DELETE FROM invitations WHERE microproject_id = ? AND email = ?", (microproject.id, user.email))
    return get_member(microproject.id, user.id)


def _owner_count(conn: sqlite3.Connection, microproject_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM memberships WHERE microproject_id = ? AND role = 'owner'", (microproject_id,)
    ).fetchone()[0]


def _check_keeps_an_owner(conn: sqlite3.Connection, microproject: Microproject, member: dict) -> None:
    """409 if ``member`` is about to lose the owner role while being the creator or the last owner."""
    if member["is_creator"]:
        raise Conflict("la personne qui a créé le µprojet en reste propriétaire", code="creator_protected")
    if member["role"] == "owner" and _owner_count(conn, microproject.id) == 1:
        raise Conflict("un µprojet garde au moins un propriétaire", code="last_owner")


def change_member_role(microproject: Microproject, user_id: int, role: str) -> dict:
    _check_role(role)
    with keyed_lock("memberships", microproject.slug), get_conn() as conn:
        member = get_member(microproject.id, user_id)
        if member["role"] == role:
            return member
        if role != "owner":
            _check_keeps_an_owner(conn, microproject, member)
        conn.execute(
            "UPDATE memberships SET role = ? WHERE microproject_id = ? AND user_id = ?", (role, microproject.id, user_id)
        )
    return get_member(microproject.id, user_id)


def remove_member(microproject: Microproject, user_id: int) -> None:
    with keyed_lock("memberships", microproject.slug), get_conn() as conn:
        _check_keeps_an_owner(conn, microproject, get_member(microproject.id, user_id))
        conn.execute("DELETE FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject.id, user_id))


# -- invitations ------------------------------------------------------------------------------------

_PENDING = "expires_at > datetime('now')"


def _invitation_from_row(row: sqlite3.Row) -> Invitation:
    return Invitation(
        id=row["id"],
        microproject_id=row["microproject_id"],
        email=row["email"],
        role=row["role"],
        invited_by=row["invited_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


def create_invitation(microproject: Microproject, email: str, role: str, *, invited_by: int) -> tuple[Invitation, str]:
    """A two-week invitation to the µprojet, and its token in clear - for the e-mail, the only
    place it goes. It replaces the pending invitation of the same address, if any (inviting again
    re-sends the link); a member is not invited (409)."""
    _check_role(role)
    email = accounts.normalize_email(email)
    if not email or "@" not in email:
        raise InvalidInput("adresse e-mail invalide", code="invalid_email")
    user = accounts.get_by_email(email)
    if user is not None and role_for(microproject.id, user.id) is not None:
        raise Conflict(f"{email} est déjà membre du µprojet", code="already_member")
    token = security.new_token()
    with get_conn() as conn:
        conn.execute("DELETE FROM invitations WHERE microproject_id = ? AND email = ?", (microproject.id, email))
        cursor = conn.execute(
            "INSERT INTO invitations (token_hash, microproject_id, email, role, invited_by, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (security.hash_token(token), microproject.id, email, role, invited_by, security.invitation_expiry()),
        )
        row = conn.execute("SELECT * FROM invitations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _invitation_from_row(row), token


def list_invitations(microproject_id: int) -> list[Invitation]:
    """The pending invitations (not yet expired), newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM invitations WHERE microproject_id = ? AND {_PENDING} ORDER BY created_at DESC, id DESC",
            (microproject_id,),
        ).fetchall()
    return [_invitation_from_row(row) for row in rows]


def cancel_invitation(microproject_id: int, invitation_id: int) -> None:
    with get_conn() as conn:
        deleted = conn.execute(
            "DELETE FROM invitations WHERE microproject_id = ? AND id = ?", (microproject_id, invitation_id)
        ).rowcount
    if not deleted:
        raise NotFound("invitation introuvable")


def get_invitation(token: str) -> Invitation | None:
    """The pending invitation an e-mailed token designates, if it is still valid."""
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT * FROM invitations WHERE token_hash = ? AND {_PENDING}", (security.hash_token(token),)
        ).fetchone()
    return _invitation_from_row(row) if row else None


def accept_invitation(invitation: Invitation, user: accounts.User) -> str:
    """Consume an invitation for a signed-in user - only if its email matches the one the
    invitation was addressed to (a token alone isn't proof of that email address, since it
    travels inside a plain URL: 403 ``email_mismatch`` otherwise). Returns the user's role in the
    microproject afterwards; every invitation of that address to the µprojet is consumed.

    An invitation never lowers a role: someone who became a member in the meantime keeps the
    higher of their current role and the invited one - a stale link must not demote the last owner.
    """
    if invitation.email != accounts.normalize_email(user.email):
        raise Forbidden("cette invitation est adressée à une autre adresse e-mail", code="email_mismatch")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM memberships WHERE microproject_id = ? AND user_id = ?", (invitation.microproject_id, user.id)
        ).fetchone()
        role = invitation.role
        if row is not None and ROLE_ORDER[row["role"]] >= ROLE_ORDER[role]:
            role = row["role"]
        conn.execute(
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(microproject_id, user_id) DO UPDATE SET role = excluded.role",
            (invitation.microproject_id, user.id, role),
        )
        conn.execute("DELETE FROM invitations WHERE microproject_id = ? AND email = ?", (invitation.microproject_id, invitation.email))
    return role


def delete(microproject: Microproject, confirm_name: str) -> None:
    """Permanently delete a microproject: its database rows (memberships and pending invitations
    cascade via the foreign keys) and the on-disk directory holding its Follow repository, saved
    structures, step presets, and tech bricks - there is no undo, this is real experiment history.
    ``confirm_name`` must match its name exactly: the page asks the owner to type it, and a raw API
    call can't skip that guard either.
    """
    if confirm_name.strip() != microproject.name:
        raise InvalidInput("le nom saisi ne correspond pas au nom du µprojet", code="confirm_name_mismatch")
    with get_conn() as conn:
        conn.execute("DELETE FROM microprojects WHERE id = ?", (microproject.id,))
    shutil.rmtree(microproject_dir(microproject.slug), ignore_errors=True)


def microproject_dir(slug: str) -> Path:
    path = data_dir() / "microprojects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path
