"""Cross-microproject links: the one relationship allowed to reach across two microprojects' otherwise
isolated Follow repositories - see the schema comment in :mod:`spectre.plugins.links.migrations` for why this
can't be a Follow reference or ride in ``Experiment.metadata`` the way same-microproject links do.
Two kinds, both symmetric (``a``/``b`` order carries no meaning): a microproject link ("these two
microprojects' work relates") and an entity link ("this physical sample relates to that one"), each
just a row plus an optional note explaining why.

An entity names a line of study (``experiment_id``, the piste), never a version: a link survives every
later write on either study. Its ``entity_index`` is a position in the piste's current
``physical_tracking`` list, checked when the link is made.

Who sees what: a link is listed only to someone who has a role in both of its microprojects
(:func:`spectre.plugins.microprojects.service.access`: a member, a manager of its team, an admin),
so it never names a microproject or a study the caller can't open. Creating one takes the editor
role on both sides (it asserts something about both); retracting one, on either side.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from ..areas import service as areas
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from ..microprojects import service as microprojects


@dataclass(frozen=True)
class MicroprojectRef:
    slug: str
    name: str


@dataclass(frozen=True)
class MicroprojectLink:
    id: int
    a: MicroprojectRef
    b: MicroprojectRef
    note: str
    created_at: str


@dataclass(frozen=True)
class EntityRef:
    microproject: str  # le slug du µprojet
    experiment_id: str  # la piste
    entity_index: int  # position dans le physical_tracking de la piste


@dataclass(frozen=True)
class EntityLink:
    id: int
    a: EntityRef
    b: EntityRef
    note: str
    created_at: str


# -- droits ---------------------------------------------------------------------------------------


def _can_edit(microproject_id: int, user: User) -> bool:
    return microprojects.has_role(user, microprojects.get_by_id(microproject_id), "editor")


def _forbidden() -> Forbidden:
    return Forbidden("vous n'avez pas les droits nécessaires pour cette action")


def _target(slug: str) -> microprojects.Microproject:
    """Un µprojet désigné dans le corps d'une création : inconnu, c'est une saisie invalide."""
    try:
        return microprojects.get_by_slug(slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise InvalidInput(f"µprojet « {slug} » introuvable", code="unknown_microproject") from exc


def _editable_target(slug: str, user: User) -> microprojects.Microproject:
    microproject = _target(slug)
    if not microprojects.has_role(user, microproject, "editor"):
        raise _forbidden()
    return microproject


def _visible_ids(user: User, *, microproject: str | None, area: str | None) -> tuple[set[int], set[int]]:
    """``(visible, wanted)`` : les µprojets où ``user`` a un rôle, et parmi eux ceux dont un lien
    doit toucher l'un au moins (tous sans filtre). ``microproject`` inconnu : 404 ; sans rôle : 403."""
    everything = microprojects.list_all()
    found = microprojects.accesses(user, everything)
    memberships = [mp for mp in everything if found[mp.id].role is not None]
    visible = {mp.id for mp in memberships}
    wanted = set(visible)
    if microproject is not None:
        try:
            target = microprojects.get_by_slug(microproject)
        except microprojects.MicroprojectNotFoundError as exc:
            raise NotFound(f"projet {microproject!r} introuvable") from exc
        if target.id not in visible:
            raise _forbidden()
        wanted = {target.id}
    if area is not None:
        area_id = areas.get_by_slug(area).id
        wanted = {mp.id for mp in memberships if mp.id in wanted and mp.management_area_id == area_id}
    return visible, wanted


def _placeholders(values: set[int]) -> str:
    return ",".join("?" * len(values))


# -- liens entre µprojets -------------------------------------------------------------------------

_MICROPROJECT_LINK_SELECT = """
SELECT link.id, link.note, link.created_at, link.microproject_a_id, link.microproject_b_id,
       a.slug AS a_slug, a.name AS a_name, b.slug AS b_slug, b.name AS b_name
FROM microproject_links AS link
JOIN microprojects AS a ON a.id = link.microproject_a_id
JOIN microprojects AS b ON b.id = link.microproject_b_id
"""


def _microproject_link_from_row(row: sqlite3.Row) -> MicroprojectLink:
    return MicroprojectLink(
        id=row["id"],
        a=MicroprojectRef(row["a_slug"], row["a_name"]),
        b=MicroprojectRef(row["b_slug"], row["b_name"]),
        note=row["note"],
        created_at=row["created_at"],
    )


def list_microproject_links(user: User, *, microproject: str | None = None, area: str | None = None) -> list[MicroprojectLink]:
    """Les liens dont ``user`` voit les deux bouts et dont l'un touche ``microproject`` (son slug)
    ou un µprojet du projet corporate ``area`` (son slug)."""
    visible, wanted = _visible_ids(user, microproject=microproject, area=area)
    if not wanted:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            f"{_MICROPROJECT_LINK_SELECT} WHERE link.microproject_a_id IN ({_placeholders(visible)}) "
            f"AND link.microproject_b_id IN ({_placeholders(visible)}) ORDER BY link.id",
            [*visible, *visible],
        ).fetchall()
    return [
        _microproject_link_from_row(row)
        for row in rows
        if row["microproject_a_id"] in wanted or row["microproject_b_id"] in wanted
    ]


def create_microproject_link(user: User, a: str, b: str, *, note: str) -> MicroprojectLink:
    microproject_a = _editable_target(a, user)
    microproject_b = _editable_target(b, user)
    if microproject_a.id == microproject_b.id:
        raise InvalidInput("un µprojet ne peut pas être lié à lui-même", code="self_link")
    try:
        with get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO microproject_links (microproject_a_id, microproject_b_id, note, created_by) VALUES (?, ?, ?, ?)",
                (microproject_a.id, microproject_b.id, note.strip(), user.id),
            )
            row = conn.execute(f"{_MICROPROJECT_LINK_SELECT} WHERE link.id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError as exc:  # l'index unique sur la paire, dans un sens ou dans l'autre
        raise Conflict("ces deux µprojets sont déjà liés", code="already_linked") from exc
    return _microproject_link_from_row(row)


def delete_microproject_link(user: User, link_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT microproject_a_id, microproject_b_id FROM microproject_links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise NotFound("lien introuvable")
    if not (_can_edit(row["microproject_a_id"], user) or _can_edit(row["microproject_b_id"], user)):
        raise _forbidden()
    with get_conn() as conn:
        conn.execute("DELETE FROM microproject_links WHERE id = ?", (link_id,))


# -- liens entre entités physiques ----------------------------------------------------------------

_ENTITY_LINK_SELECT = """
SELECT link.*, a.slug AS a_slug, b.slug AS b_slug
FROM entity_links AS link
JOIN microprojects AS a ON a.id = link.a_microproject_id
JOIN microprojects AS b ON b.id = link.b_microproject_id
"""


def _entity_link_from_row(row: sqlite3.Row) -> EntityLink:
    return EntityLink(
        id=row["id"],
        a=EntityRef(row["a_slug"], row["a_experiment_id"], row["a_entity_index"]),
        b=EntityRef(row["b_slug"], row["b_experiment_id"], row["b_entity_index"]),
        note=row["note"],
        created_at=row["created_at"],
    )


def list_entity_links(user: User, *, microproject: str | None = None, area: str | None = None) -> list[EntityLink]:
    """Comme :func:`list_microproject_links`, pour les liens entre entités."""
    visible, wanted = _visible_ids(user, microproject=microproject, area=area)
    if not wanted:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            f"{_ENTITY_LINK_SELECT} WHERE link.a_microproject_id IN ({_placeholders(visible)}) "
            f"AND link.b_microproject_id IN ({_placeholders(visible)}) ORDER BY link.id",
            [*visible, *visible],
        ).fetchall()
    return [_entity_link_from_row(row) for row in rows if row["a_microproject_id"] in wanted or row["b_microproject_id"] in wanted]


def _check_entity(microproject: microprojects.Microproject, ref: EntityRef) -> None:
    """La piste existe dans ce µprojet et y suit une entité à cet index - sinon 422."""
    try:
        tip = experiments.tip_of(get_repository(microproject.slug), ref.experiment_id)
    except NotFound as exc:
        raise InvalidInput(f"expérience « {ref.experiment_id} » introuvable dans « {microproject.slug} »", code="unknown_experiment") from exc
    if not 0 <= ref.entity_index < len(tip.metadata.get("physical_tracking", [])):
        raise InvalidInput(f"l'expérience « {ref.experiment_id} » ne suit aucune entité n° {ref.entity_index}", code="unknown_entity")


def create_entity_link(user: User, a: EntityRef, b: EntityRef, *, note: str) -> EntityLink:
    microproject_a = _editable_target(a.microproject, user)
    microproject_b = _editable_target(b.microproject, user)
    if a == b:
        raise InvalidInput("une entité ne peut pas être liée à elle-même", code="self_link")
    _check_entity(microproject_a, a)
    _check_entity(microproject_b, b)
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO entity_links (a_microproject_id, a_experiment_id, a_entity_index, "
            "b_microproject_id, b_experiment_id, b_entity_index, note, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (microproject_a.id, a.experiment_id, a.entity_index, microproject_b.id, b.experiment_id, b.entity_index, note.strip(), user.id),
        )
        row = conn.execute(f"{_ENTITY_LINK_SELECT} WHERE link.id = ?", (cursor.lastrowid,)).fetchone()
    return _entity_link_from_row(row)


def delete_entity_link(user: User, link_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT a_microproject_id, b_microproject_id FROM entity_links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise NotFound("lien introuvable")
    if not (_can_edit(row["a_microproject_id"], user) or _can_edit(row["b_microproject_id"], user)):
        raise _forbidden()
    with get_conn() as conn:
        conn.execute("DELETE FROM entity_links WHERE id = ?", (link_id,))
