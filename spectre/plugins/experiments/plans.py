"""Les expériences prévisionnelles d'un µprojet : prévues depuis son arbre, avant d'en savoir la
structure, le split ou les plaques réelles - un titre, une intention, et ce qu'elle continue :

- **les mêmes plaques** (``same_wafers``) : une ou plusieurs plaques de la version dont elle part,
  qui y subiront des tests supplémentaires - lancée, elle part de ces plaques (``wafer_origin``) ;
- **de nouvelles plaques** (``new_wafers``) : le nombre qu'on pense lancer, une estimation - lancée,
  elle part de la structure de cette version (``from_version``), ou de rien pour une racine.

Elle peut aussi partir d'une autre expérience prévue (``parent_plan_id``) : elle continue ce que
celle-ci donnera - ses plaques si elle les nomme, sinon des plaques qu'on cochera plus tard (mêmes
plaques), ou sa structure (nouvelles plaques). Elle ne se lance qu'après elle : la mère lancée, ses
filles partent de la nouvelle étude. La mère supprimée, ses filles restent, **détachées**
(``detached_from`` : le titre de la mère) - on les rattache ensuite à la main (``PATCH`` avec
``parent`` ou ``parent_plan_id``).

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
    parent_plan_id: int | None
    detached_from: str | None
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
            "parent_plan_id": self.parent_plan_id,
            "detached_from": self.detached_from,
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
        parent_plan_id=row["parent_plan_id"],
        detached_from=row["detached_from"],
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


def _descendants(microproject_id: int, plan_id: int) -> set[int]:
    """Les prévisions qui partent, de proche en proche, de ``plan_id`` (elle comprise)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, parent_plan_id FROM experiment_plans WHERE microproject_id = ?", (microproject_id,)).fetchall()
    children: dict[int, list[int]] = {}
    for row in rows:
        if row["parent_plan_id"] is not None:
            children.setdefault(row["parent_plan_id"], []).append(row["id"])
    found, frontier = {plan_id}, [plan_id]
    while frontier:
        for child in children.get(frontier.pop(), []):
            if child not in found:
                found.add(child)
                frontier.append(child)
    return found


def _parent_plan(microproject_id: int, parent_plan_id: int, *, of: int | None = None) -> Plan:
    """L'expérience prévue dont part une prévision - pour ``of``, qu'on rattache : ni elle-même ni
    une de celles qui en partent."""
    try:
        parent = get_plan(microproject_id, parent_plan_id)
    except NotFound as exc:
        raise NotFound("Expérience prévue de départ introuvable.", code="source_not_found") from exc
    if of is not None and parent.id in _descendants(microproject_id, of):
        raise InvalidInput("Une prévision ne peut partir ni d'elle-même ni d'une prévision qui en découle.", code="plan_cycle")
    return parent


def _distinct(wafers: list[str]) -> list[str]:
    seen: set[str] = set()
    kept = []
    for mark in (w.strip() for w in wafers):
        if mark and compact(mark) not in seen:
            seen.add(compact(mark))
            kept.append(mark)
    return kept


def _checked_wafers(slug: str, parent: follow.Experiment, wafers: list[str]) -> list[str]:
    """Les plaques reprises de ``parent`` (sans doublon, dans l'ordre donné) : au moins une, toutes
    suivies par cette version, et d'une même variante pour une campagne - la règle d'un départ de
    plaques existantes (:func:`service.resolve_wafer_origin`), vérifiée dès la prévision."""
    kept = _distinct(wafers)
    if not kept:
        raise InvalidInput("Cochez au moins une plaque de l'expérience de départ.", code="entity_required")
    origin = WaferOrigin(microproject=slug, experiment_id=parent.branch, version_id=parent.id)
    service.resolve_wafer_origin(get_repository(slug), origin, [{"sample_id": mark} for mark in kept])
    return kept


def _checked_plan_wafers(parent: Plan, wafers: list[str]) -> list[str]:
    """Les plaques reprises d'une expérience prévue (``parent``) : parmi celles qu'elle nomme, au
    moins une. Si elle n'en nomme pas (de nouvelles plaques, pas encore nommées), aucune : on les
    cochera une fois qu'elle sera lancée."""
    if not parent.wafers:
        return []
    kept = _distinct(wafers)
    if not kept:
        raise InvalidInput("Cochez au moins une plaque de l'expérience prévue dont elle part.", code="entity_required")
    known = {compact(mark) for mark in parent.wafers}
    missing = [mark for mark in kept if compact(mark) not in known]
    if missing:
        raise InvalidInput(f"L'expérience prévue de départ ne reprend pas : {', '.join(missing)}.", code="wafer_not_in_origin")
    return kept


def _same_wafers(slug: str, version: follow.Experiment | None, parent_plan: Plan | None, wafers: list[str]) -> list[str]:
    if version is not None:
        return _checked_wafers(slug, version, wafers)
    if parent_plan is not None:
        return _checked_plan_wafers(parent_plan, wafers)
    raise InvalidInput("Reprendre des plaques suppose une expérience de départ.", code="parent_required")


def _checked_count(count: int | None) -> int:
    if count is None or count < 1:
        raise InvalidInput("Indiquez le nombre de plaques prévues (au moins une).", code="wafer_count_required")
    return count


def _one_parent(parent: Any, parent_plan_id: int | None) -> None:
    if parent is not None and parent_plan_id is not None:
        raise InvalidInput("Une prévision part d'une étude ou d'une autre prévision, pas des deux.", code="parent_conflict")


def create_plan(microproject_id: int, slug: str, body: PlanRequest, *, user_id: int, author: str) -> Plan:
    """Une expérience prévue : à la suite d'une version (``parent``) ou d'une autre prévision
    (``parent_plan_id``), sur ses plaques ou sur de nouvelles, ou en racine (de nouvelles plaques
    seulement)."""
    title, intent = body.title.strip(), body.intent.strip()
    if not title:
        raise InvalidInput("Le titre est obligatoire.", code="title_required")
    _one_parent(body.parent, body.parent_plan_id)
    parent = _parent_version(slug, body.parent.experiment_id, body.parent.version_id) if body.parent else None
    parent_plan = _parent_plan(microproject_id, body.parent_plan_id) if body.parent_plan_id is not None else None
    wafers: list[str] = []
    count = None
    if body.mode == "same_wafers":
        wafers = _same_wafers(slug, parent, parent_plan, body.wafers)
    else:
        count = _checked_count(body.wafer_count)
    now = _now()
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO experiment_plans (microproject_id, title, intent, parent_experiment_id, parent_version_id, parent_plan_id, mode,
                                             wafers, wafer_count, created_by, author, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                microproject_id, title, intent, parent.branch if parent else None, parent.id if parent else None,
                parent_plan.id if parent_plan else None, body.mode, json.dumps(wafers), count, user_id, author, now, now,
            ),
        )
        plan_id = cursor.lastrowid
    return get_plan(microproject_id, plan_id)


def update_plan(microproject_id: int, slug: str, plan_id: int, changes: PlanUpdate) -> Plan:
    """Titre, intention, mode et plaques (reprises ou nombre prévu). Le point de départ reste, sauf
    avec ``parent`` ou ``parent_plan_id`` : la prévision est rattachée (une détachée, d'ordinaire)
    sous cette version ou cette prévision - les deux à ``null``, elle devient une racine. Une
    prévision détachée sur les mêmes plaques les garde telles quelles jusqu'à son rattachement."""
    plan = get_plan(microproject_id, plan_id)
    title = changes.title.strip() if changes.title is not None else plan.title
    if not title:
        raise InvalidInput("Le titre est obligatoire.", code="title_required")
    intent = changes.intent.strip() if changes.intent is not None else plan.intent
    mode = changes.mode or plan.mode
    reattach = bool({"parent", "parent_plan_id"} & changes.model_fields_set)
    if reattach:
        _one_parent(changes.parent, changes.parent_plan_id)
        version = _parent_version(slug, changes.parent.experiment_id, changes.parent.version_id) if changes.parent else None
        parent_plan = _parent_plan(microproject_id, changes.parent_plan_id, of=plan.id) if changes.parent_plan_id is not None else None
        detached_from = None
    else:
        version, parent_plan, detached_from = None, None, plan.detached_from
    if mode == "same_wafers":
        wafers = plan.wafers
        if reattach or changes.wafers is not None or mode != plan.mode:
            if not reattach and plan.parent_version_id is not None:
                version = _parent_version(slug, plan.parent_experiment_id, plan.parent_version_id)
            elif not reattach and plan.parent_plan_id is not None:
                parent_plan = _parent_plan(microproject_id, plan.parent_plan_id)
            if version is None and parent_plan is None and detached_from is not None and mode == plan.mode:
                wafers = _distinct(changes.wafers) if changes.wafers is not None else plan.wafers  # détachée : en attente d'un rattachement
            else:
                given = changes.wafers if changes.wafers is not None else (plan.wafers if reattach else [])
                wafers = _same_wafers(slug, version, parent_plan, given)
        count = None
    else:
        count = _checked_count(changes.wafer_count if changes.wafer_count is not None else plan.wafer_count)
        wafers = []
    if reattach:
        experiment_id, version_id = (version.branch, version.id) if version else (None, None)
        parent_plan_id = parent_plan.id if parent_plan else None
    else:
        experiment_id, version_id, parent_plan_id = plan.parent_experiment_id, plan.parent_version_id, plan.parent_plan_id
    with get_conn() as conn:
        conn.execute(
            """UPDATE experiment_plans SET title = ?, intent = ?, parent_experiment_id = ?, parent_version_id = ?, parent_plan_id = ?,
                                           detached_from = ?, mode = ?, wafers = ?, wafer_count = ?, updated_at = ? WHERE id = ?""",
            (title, intent, experiment_id, version_id, parent_plan_id, detached_from, mode, json.dumps(wafers), count, _now(), plan_id),
        )
    return get_plan(microproject_id, plan_id)


def delete_plan(microproject_id: int, plan_id: int) -> None:
    """Supprimer une prévision : celles qui en partent restent, détachées (``detached_from`` : son
    titre), jusqu'à ce qu'on les rattache à la main."""
    plan = get_plan(microproject_id, plan_id)
    with get_conn() as conn:
        conn.execute(
            "UPDATE experiment_plans SET parent_plan_id = NULL, detached_from = ?, updated_at = ? WHERE parent_plan_id = ? AND microproject_id = ?",
            (plan.title, _now(), plan_id, microproject_id),
        )
        conn.execute("DELETE FROM experiment_plans WHERE id = ?", (plan_id,))


def consume_plan(microproject_id: int, plan_id: int, *, experiment_id: str, version_id: str) -> None:
    """L'expérience prévue vient d'être lancée (l'étude ``experiment_id``, à sa version
    ``version_id``) : elle n'est plus prévisionnelle, et celles qui en partaient partent maintenant
    de cette étude (déjà retirée : rien à faire - l'étude est créée de toute façon)."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE experiment_plans SET parent_plan_id = NULL, parent_experiment_id = ?, parent_version_id = ?, updated_at = ?
               WHERE parent_plan_id = ? AND microproject_id = ?""",
            (experiment_id, version_id, _now(), plan_id, microproject_id),
        )
        conn.execute("DELETE FROM experiment_plans WHERE id = ? AND microproject_id = ?", (plan_id, microproject_id))
