"""Les expériences prévisionnelles d'un µprojet : prévues depuis son arbre, avant d'en savoir la
structure, le split ou les plaques réelles - un titre, une intention, et ce qu'elle continue :

- **les mêmes plaques** (``same_wafers``) : une ou plusieurs plaques de la version dont elle part,
  qui y subiront des tests supplémentaires - lancée, elle part de ces plaques (``wafer_origin``) ;
- **de nouvelles plaques** (``new_wafers``) : le nombre qu'on pense lancer, une estimation - lancée,
  elle part de la structure de cette version (``from_version``), ou de rien pour une racine.

Elle vit ici, dans la base, et non dans le dépôt Follow : ce n'est pas encore une étude. Lancée
(``POST .../experiments`` avec son ``plan_id``), elle est supprimée - l'étude ne garde que ses
plaques réelles. La version dont elle part reste celle choisie, même si la piste avance ensuite.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import follow

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput, NotFound
from . import service
from .entities import compact
from .repository import get_repository
from .schemas import PlanRequest, PlanUpdate, WaferOrigin

MODES = ("same_wafers", "new_wafers")


@dataclass(frozen=True)
class Plan:
    id: int
    microproject_id: int
    title: str
    intent: str
    parent_experiment_id: str | None
    parent_version_id: str | None
    mode: str
    wafers: list[str]
    wafer_count: int | None
    author: str
    created_at: str
    updated_at: str

    def payload(self) -> dict[str, Any]:
        parent = {"experiment_id": self.parent_experiment_id, "version_id": self.parent_version_id} if self.parent_version_id else None
        return {
            "id": self.id,
            "title": self.title,
            "intent": self.intent,
            "parent": parent,
            "mode": self.mode,
            "wafers": list(self.wafers),
            "wafer_count": self.wafer_count,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _plan_from_row(row: sqlite3.Row) -> Plan:
    return Plan(
        id=row["id"],
        microproject_id=row["microproject_id"],
        title=row["title"],
        intent=row["intent"],
        parent_experiment_id=row["parent_experiment_id"],
        parent_version_id=row["parent_version_id"],
        mode=row["mode"],
        wafers=json.loads(row["wafers"] or "[]"),
        wafer_count=row["wafer_count"],
        author=row["author"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_plans(microproject_id: int) -> list[Plan]:
    """Les expériences prévisionnelles du µprojet, les plus anciennes d'abord."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM experiment_plans WHERE microproject_id = ? ORDER BY created_at, id", (microproject_id,)).fetchall()
    return [_plan_from_row(row) for row in rows]


def get_plan(microproject_id: int, plan_id: int) -> Plan:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM experiment_plans WHERE id = ? AND microproject_id = ?", (plan_id, microproject_id)).fetchone()
    if row is None:
        raise NotFound("Expérience prévisionnelle introuvable.", code="plan_not_found")
    return _plan_from_row(row)


def _parent_version(slug: str, experiment_id: str, version_id: str | None) -> follow.Experiment:
    """La version dont part l'expérience prévue (la pointe de la piste sans ``version_id``)."""
    try:
        return service.version_of(get_repository(slug), experiment_id, version_id)
    except NotFound as exc:
        raise NotFound(f"Expérience de départ introuvable : {exc}", code="source_not_found") from exc


def _checked_wafers(slug: str, parent: follow.Experiment, wafers: list[str]) -> list[str]:
    """Les plaques reprises de ``parent`` (sans doublon, dans l'ordre donné) : au moins une, toutes
    suivies par cette version, et d'une même variante pour une campagne - la règle d'un départ de
    plaques existantes (:func:`service.resolve_wafer_origin`), vérifiée dès la prévision."""
    seen: set[str] = set()
    kept = []
    for mark in (w.strip() for w in wafers):
        if mark and compact(mark) not in seen:
            seen.add(compact(mark))
            kept.append(mark)
    if not kept:
        raise InvalidInput("Cochez au moins une plaque de l'expérience de départ.", code="entity_required")
    origin = WaferOrigin(microproject=slug, experiment_id=parent.branch, version_id=parent.id)
    service.resolve_wafer_origin(get_repository(slug), origin, [{"sample_id": mark} for mark in kept])
    return kept


def _checked_count(count: int | None) -> int:
    if count is None or count < 1:
        raise InvalidInput("Indiquez le nombre de plaques prévues (au moins une).", code="wafer_count_required")
    return count


def create_plan(microproject_id: int, slug: str, body: PlanRequest, *, user_id: int, author: str) -> Plan:
    """Une expérience prévue : à la suite d'une version (``parent``), sur ses plaques ou sur de
    nouvelles, ou en racine (de nouvelles plaques seulement)."""
    title, intent = body.title.strip(), body.intent.strip()
    if not title:
        raise InvalidInput("Le titre est obligatoire.", code="title_required")
    parent = _parent_version(slug, body.parent.experiment_id, body.parent.version_id) if body.parent else None
    wafers: list[str] = []
    count = None
    if body.mode == "same_wafers":
        if parent is None:
            raise InvalidInput("Reprendre des plaques suppose une expérience de départ.", code="parent_required")
        wafers = _checked_wafers(slug, parent, body.wafers)
    else:
        count = _checked_count(body.wafer_count)
    now = _now()
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO experiment_plans (microproject_id, title, intent, parent_experiment_id, parent_version_id, mode, wafers,
                                             wafer_count, created_by, author, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                microproject_id, title, intent, parent.branch if parent else None, parent.id if parent else None, body.mode,
                json.dumps(wafers), count, user_id, author, now, now,
            ),
        )
        plan_id = cursor.lastrowid
    return get_plan(microproject_id, plan_id)


def update_plan(microproject_id: int, slug: str, plan_id: int, changes: PlanUpdate) -> Plan:
    """Titre, intention, mode et plaques (reprises ou nombre prévu) - la version de départ reste."""
    plan = get_plan(microproject_id, plan_id)
    title = changes.title.strip() if changes.title is not None else plan.title
    if not title:
        raise InvalidInput("Le titre est obligatoire.", code="title_required")
    intent = changes.intent.strip() if changes.intent is not None else plan.intent
    mode = changes.mode or plan.mode
    wafers, count = plan.wafers, plan.wafer_count
    if mode == "same_wafers":
        if plan.parent_version_id is None:
            raise InvalidInput("Reprendre des plaques suppose une expérience de départ.", code="parent_required")
        if changes.wafers is not None or mode != plan.mode:
            parent = _parent_version(slug, plan.parent_experiment_id, plan.parent_version_id)
            wafers = _checked_wafers(slug, parent, changes.wafers or [])
        count = None
    else:
        count = _checked_count(changes.wafer_count if changes.wafer_count is not None else plan.wafer_count)
        wafers = []
    with get_conn() as conn:
        conn.execute(
            "UPDATE experiment_plans SET title = ?, intent = ?, mode = ?, wafers = ?, wafer_count = ?, updated_at = ? WHERE id = ?",
            (title, intent, mode, json.dumps(wafers), count, _now(), plan_id),
        )
    return get_plan(microproject_id, plan_id)


def delete_plan(microproject_id: int, plan_id: int) -> None:
    get_plan(microproject_id, plan_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM experiment_plans WHERE id = ?", (plan_id,))


def consume_plan(microproject_id: int, plan_id: int) -> None:
    """L'expérience prévue vient d'être lancée : elle n'est plus prévisionnelle (déjà retirée :
    rien à faire - l'étude est créée de toute façon)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM experiment_plans WHERE id = ? AND microproject_id = ?", (plan_id, microproject_id))
