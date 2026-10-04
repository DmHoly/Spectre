"""Teams: who manages what. A team groups accounts, each a ``manager`` or a plain ``member`` of
it; an account may belong to several teams and manage only some of them. What a team owns - its
corporate projects, hence their µprojets - is said by the plugins above this one
(``management_areas.team_id``, :func:`spectre.plugins.areas.service.can_manage`): this module only
knows the teams and their members.

Who may change a team: an admin (``users.is_admin``) creates, renames and deletes teams; an admin
or one of its managers manages its members (:func:`can_manage`). A team that has managers keeps at
least one (:func:`change_member_role`, :func:`remove_member`: 409 ``last_manager``).
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ...kernel.locks import keyed_lock
from ..accounts import service as accounts
from ..accounts.service import User

TEAM_ROLES = ("manager", "member")


class TeamNotFoundError(NotFound):
    pass


@dataclass(frozen=True)
class Team:
    id: int
    slug: str
    name: str
    created_at: str


def _team_from_row(row: sqlite3.Row) -> Team:
    return Team(row["id"], row["slug"], row["name"], row["created_at"])


def _slug_base(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-") or "equipe"


def _required_name(name: str | None) -> str:
    name = (name or "").strip()
    if not name:
        raise InvalidInput("le nom de l'équipe est obligatoire")
    return name


# -- équipes ----------------------------------------------------------------------------------------


def list_all() -> list[Team]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY name COLLATE NOCASE, id").fetchall()
    return [_team_from_row(row) for row in rows]


def get_by_slug(slug: str) -> Team:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM teams WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise TeamNotFoundError(f"équipe {slug!r} introuvable")
    return _team_from_row(row)


def get_by_id(team_id: int) -> Team:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if row is None:
        raise TeamNotFoundError(f"équipe n° {team_id} introuvable")
    return _team_from_row(row)


def create(name: str) -> Team:
    """A new team, without members: its slug comes from its name (« -2 »... if taken)."""
    name = _required_name(name)
    base = _slug_base(name)
    with get_conn() as conn:
        slug, suffix = base, 2
        while conn.execute("SELECT 1 FROM teams WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        cursor = conn.execute("INSERT INTO teams (slug, name) VALUES (?, ?)", (slug, name))
        team_id = cursor.lastrowid
    return get_by_id(team_id)


def rename(team: Team, name: str) -> Team:
    """The slug stays: links to the team keep working."""
    name = _required_name(name)
    with get_conn() as conn:
        conn.execute("UPDATE teams SET name = ? WHERE id = ?", (name, team.id))
    return get_by_id(team.id)


def delete(team: Team) -> None:
    """Its members go with it; the projects it owned stay, without a team (``ON DELETE SET NULL``)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM teams WHERE id = ?", (team.id,))


# -- droits -----------------------------------------------------------------------------------------


def managed_team_ids(user_id: int) -> set[int]:
    """The teams ``user_id`` manages."""
    with get_conn() as conn:
        rows = conn.execute("SELECT team_id FROM team_members WHERE user_id = ? AND role = 'manager'", (user_id,)).fetchall()
    return {row["team_id"] for row in rows}


def roles_of(user_id: int) -> dict[int, str]:
    """``{team_id: role}`` of every team ``user_id`` belongs to."""
    with get_conn() as conn:
        rows = conn.execute("SELECT team_id, role FROM team_members WHERE user_id = ?", (user_id,)).fetchall()
    return {row["team_id"]: row["role"] for row in rows}


def can_manage(user: User, team: Team) -> bool:
    """An admin, or a manager of this team: they manage its members."""
    return user.is_admin or team.id in managed_team_ids(user.id)


def require_manage(user: User, team: Team) -> None:
    if not can_manage(user, team):
        raise Forbidden("seuls un administrateur ou un manager de cette équipe peuvent gérer ses membres")


# -- membres ----------------------------------------------------------------------------------------

_MEMBER_SELECT = (
    "SELECT users.id, users.name, users.email, team_members.role FROM team_members "
    "JOIN users ON users.id = team_members.user_id "
)


def _check_role(role: str) -> None:
    if role not in TEAM_ROLES:
        raise InvalidInput(f"rôle d'équipe inconnu : {role!r} (manager ou member)")


def list_members(team_id: int) -> list[dict]:
    """``[{id, name, email, role}]``: the managers first, then by name."""
    with get_conn() as conn:
        rows = conn.execute(
            _MEMBER_SELECT + "WHERE team_members.team_id = ? ORDER BY team_members.role != 'manager', users.name COLLATE NOCASE",
            (team_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_member(team_id: int, user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(_MEMBER_SELECT + "WHERE team_members.team_id = ? AND team_members.user_id = ?", (team_id, user_id)).fetchone()
    if row is None:
        raise NotFound("cette personne n'est pas membre de l'équipe")
    return dict(row)


def summaries(team_ids: list[int]) -> dict[int, dict]:
    """``{team_id: {member_count, managers: [{id, name}]}}`` - one query for a whole list."""
    found: dict[int, dict] = {team_id: {"member_count": 0, "managers": []} for team_id in team_ids}
    if not team_ids:
        return found
    placeholders = ",".join("?" * len(team_ids))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT team_members.team_id, team_members.role, users.id, users.name FROM team_members "
            f"JOIN users ON users.id = team_members.user_id WHERE team_members.team_id IN ({placeholders}) "
            "ORDER BY users.name COLLATE NOCASE",
            list(team_ids),
        ).fetchall()
    for row in rows:
        summary = found[row["team_id"]]
        summary["member_count"] += 1
        if row["role"] == "manager":
            summary["managers"].append({"id": row["id"], "name": row["name"]})
    return found


def add_member(team: Team, email: str, role: str) -> dict:
    """Add the account of ``email`` - 404 ``no_account`` if there is none, 409 ``already_member``."""
    _check_role(role)
    user = accounts.get_by_email(email)
    if user is None:
        raise NotFound(f"aucun compte n'existe pour {accounts.normalize_email(email)!r}", code="no_account")
    with get_conn() as conn:
        try:
            conn.execute("INSERT INTO team_members (team_id, user_id, role) VALUES (?, ?, ?)", (team.id, user.id, role))
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"{user.email} est déjà membre de l'équipe", code="already_member") from exc
    return get_member(team.id, user.id)


def _check_keeps_a_manager(conn: sqlite3.Connection, team: Team, member: dict) -> None:
    if member["role"] != "manager":
        return
    managers = conn.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ? AND role = 'manager'", (team.id,)).fetchone()[0]
    if managers == 1:
        raise Conflict("une équipe garde au moins un manager : nommez-en un autre d'abord", code="last_manager")


def change_member_role(team: Team, user_id: int, role: str) -> dict:
    _check_role(role)
    with keyed_lock("team_members", team.slug), get_conn() as conn:
        member = get_member(team.id, user_id)
        if member["role"] == role:
            return member
        _check_keeps_a_manager(conn, team, member)
        conn.execute("UPDATE team_members SET role = ? WHERE team_id = ? AND user_id = ?", (role, team.id, user_id))
    return get_member(team.id, user_id)


def remove_member(team: Team, user_id: int) -> None:
    with keyed_lock("team_members", team.slug), get_conn() as conn:
        _check_keeps_a_manager(conn, team, get_member(team.id, user_id))
        conn.execute("DELETE FROM team_members WHERE team_id = ? AND user_id = ?", (team.id, user_id))
