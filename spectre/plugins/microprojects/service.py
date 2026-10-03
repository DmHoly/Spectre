"""Microprojects and membership - the data-access layer over the ``microprojects``/``memberships`` tables,
plus each microproject's own directory on disk (:func:`microproject_dir`), under which the other
plugins keep its Follow repository, saved structures, step presets and attachments. Follow and
StructureForge never know a "microproject" exists; the plugins map a slug to the paths they're given
from here.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ...kernel import mail
from ...kernel.db import data_dir, get_conn
from ...kernel.errors import Forbidden, InvalidInput, NotFound
from ..accounts import security
from ..accounts import service as accounts
from ..areas import service as areas
from ..areas.service import slugify

ROLE_ORDER = {"viewer": 0, "editor": 1, "owner": 2}


class MicroprojectNotFoundError(Exception):
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
    exact = None
    try:
        exact = get_by_code(text)
    except MicroprojectNotFoundError:
        pass
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
    if not match:
        raise MicroprojectNotFoundError(text)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM microprojects WHERE lower(code_prefix) = lower(?) AND code_number = ?",
            (match.group(1), int(match.group(2))),
        ).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(text)
    return _microproject_from_row(row)


def _slugify(name: str) -> str:
    return slugify(name) or "microprojet"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM microprojects WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def create(
    name: str,
    description: str,
    *,
    owner_id: int,
    management_area_id: int | None = None,
    thematic_id: int | None = None,
) -> Microproject:
    name = name.strip()
    if not name:
        raise ValueError("le nom du µprojet est obligatoire")
    with get_conn() as conn:
        if management_area_id is None:
            management_area_id = conn.execute(
                "SELECT id FROM management_areas WHERE slug = ?", ("non-classe",)
            ).fetchone()["id"]
        slug = _unique_slug(conn, _slugify(name))
        cursor = conn.execute(
            "INSERT INTO microprojects (slug, name, description, management_area_id, thematic_id, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slug, name, description.strip(), management_area_id, thematic_id, owner_id),
        )
        microproject_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, 'owner')",
            (microproject_id, owner_id),
        )
        assign_code(conn, microproject_id, management_area_id)
    microproject_dir(slug)  # create the on-disk home for this microproject's Follow repo/structures upfront
    return get_by_id(microproject_id)


def set_management_area(microproject_id: int, management_area_id: int, thematic_id: int | None = None) -> None:
    """Move a µprojet to an area and, optionally, one of its thématiques - the caller checks that
    ``thematic_id`` belongs to ``management_area_id``."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE microprojects SET management_area_id = ?, thematic_id = ? WHERE id = ?",
            (management_area_id, thematic_id, microproject_id),
        )
        assign_code(conn, microproject_id, management_area_id)  # numbered on first landing in a numbered project


def update(slug: str, user: accounts.User, changes: dict) -> Microproject:
    """Only the fields given change: ``name``, ``description``, and where the µprojet sits -
    ``area`` (a project's slug; changing project drops its thématique) and ``thematic`` (the slug
    of one of that project's thématiques, or ``None``). Its owners and the strategy-layer admins
    only."""
    try:
        microproject = get_by_slug(slug)
    except MicroprojectNotFoundError as exc:
        raise NotFound(f"µprojet {slug!r} introuvable") from exc
    if not (user.is_admin or role_for(microproject.id, user.id) == "owner"):
        raise Forbidden("seuls un propriétaire du µprojet ou un administrateur peuvent le modifier")

    name, description = microproject.name, microproject.description
    if changes.get("name") is not None:
        name = changes["name"].strip()
        if not name:
            raise InvalidInput("le nom du µprojet est obligatoire")
    if changes.get("description") is not None:
        description = changes["description"].strip()
    area_id, thematic_id = microproject.management_area_id, microproject.thematic_id
    if "area" in changes:
        if not changes["area"]:
            raise InvalidInput("un µprojet appartient toujours à un projet")
        try:
            area_id = areas.get_by_slug(changes["area"]).id
        except areas.ManagementAreaNotFoundError as exc:
            raise InvalidInput(f"projet {changes['area']!r} introuvable") from exc
        if area_id != microproject.management_area_id:
            thematic_id = None
    if "thematic" in changes:
        thematic_id = None
        if changes["thematic"]:
            try:
                thematic_id = areas.get_thematic(area_id, changes["thematic"]).id
            except areas.ThematicNotFoundError as exc:
                raise InvalidInput(f"la thématique {changes['thematic']!r} n'appartient pas à ce projet") from exc

    with get_conn() as conn:
        conn.execute("UPDATE microprojects SET name = ?, description = ? WHERE id = ?", (name, description, microproject.id))
    if (area_id, thematic_id) != (microproject.management_area_id, microproject.thematic_id):
        set_management_area(microproject.id, area_id, thematic_id)
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
        raise MicroprojectNotFoundError(slug)
    return _microproject_from_row(row)


def get_by_id(microproject_id: int) -> Microproject:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM microprojects WHERE id = ?", (microproject_id,)).fetchone()
    if row is None:
        raise MicroprojectNotFoundError(str(microproject_id))
    return _microproject_from_row(row)


def list_for_user(user_id: int) -> list[tuple[Microproject, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT microprojects.*, memberships.role AS role FROM microprojects "
            "JOIN memberships ON memberships.microproject_id = microprojects.id "
            "WHERE memberships.user_id = ? ORDER BY microprojects.created_at DESC",
            (user_id,),
        ).fetchall()
    return [(_microproject_from_row(row), row["role"]) for row in rows]


def role_for(microproject_id: int, user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject_id, user_id)
        ).fetchone()
    return row["role"] if row else None


def list_members(microproject_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT users.id, users.name, users.email, memberships.role FROM memberships "
            "JOIN users ON users.id = memberships.user_id WHERE memberships.microproject_id = ? "
            "ORDER BY users.name",
            (microproject_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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


def add_member(microproject_id: int, microproject_name: str, email: str, role: str, *, invited_by: int) -> str:
    """Add ``email`` to the microproject directly if they already have an account (returns
    ``"added"``), or create a two-week invitation and e-mail them a signup link otherwise
    (returns ``"invited"``) - see :func:`accept_invitation` for the other end of that link.
    """
    if role not in ROLE_ORDER:
        raise ValueError(f"rôle inconnu : {role!r}")
    email = email.strip().lower()
    user = accounts.get_by_email(email)
    if user is not None:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?) "
                "ON CONFLICT(microproject_id, user_id) DO UPDATE SET role = excluded.role",
                (microproject_id, user.id, role),
            )
        return "added"

    token = security.new_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO invitations (token, microproject_id, email, role, invited_by, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (token, microproject_id, email, role, invited_by, security.invitation_expiry()),
        )
    inviter = accounts.get_by_id(invited_by)
    link = f"{mail.base_url()}/inscription?invitation={token}"
    mail.send_email(
        email,
        f"Invitation à rejoindre « {microproject_name} » sur Spectre",
        f"{inviter.name if inviter else 'Un membre'} vous invite à rejoindre le projet "
        f"« {microproject_name} » sur Spectre.\n\n"
        f"Pour créer votre compte et rejoindre le projet, ouvrez ce lien (valable 14 jours) :\n{link}",
    )
    return "invited"


def remove_member(microproject_id: int, user_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM memberships WHERE microproject_id = ? AND user_id = ?", (microproject_id, user_id))


def list_invitations(microproject_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT token, email, role, created_at FROM invitations WHERE microproject_id = ? ORDER BY created_at DESC",
            (microproject_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def cancel_invitation(microproject_id: int, token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM invitations WHERE microproject_id = ? AND token = ?", (microproject_id, token))


def get_invitation(token: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT invitations.token, invitations.email, invitations.role, invitations.microproject_id, "
            "microprojects.name AS microproject_name FROM invitations JOIN microprojects ON microprojects.id = invitations.microproject_id "
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
            "INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(microproject_id, user_id) DO UPDATE SET role = excluded.role",
            (invitation["microproject_id"], user_id, invitation["role"]),
        )
        conn.execute("DELETE FROM invitations WHERE token = ?", (token,))
    return True


def delete(microproject: Microproject) -> None:
    """Permanently delete a microproject: its database rows (memberships and pending invitations
    cascade via the foreign keys) and the on-disk directory holding its Follow repository, saved
    structures, step presets, and tech bricks - there is no undo, this is real experiment history.
    """
    import shutil

    with get_conn() as conn:
        conn.execute("DELETE FROM microprojects WHERE id = ?", (microproject.id,))
    shutil.rmtree(microproject_dir(microproject.slug), ignore_errors=True)


def microproject_dir(slug: str) -> Path:
    path = data_dir() / "microprojects" / slug
    path.mkdir(parents=True, exist_ok=True)
    return path

