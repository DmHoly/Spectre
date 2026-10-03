"""Suivi de lots (:mod:`spectre.plugins.lots.service`) : la liste (vue Gantt), la fiche d'un lot, la recherche de
la topbar, et la saisie déclarative (priorité P10/P20..., début, fin prévisionnelle, fin déclarée,
wafers, thématiques visées).

Ce que la base ne stocke pas est déduit ici, à chaque lecture : les **expériences** d'un lot sont
les études (pointes de branche, comme l'index des plaques) qui suivent un de ses wafers - toutes,
même terminées avant que le wafer n'y entre -, et ses
**thématiques** celles des µprojets de ces études, plus les thématiques déclarées à la main. Comme
la page d'une thématique, un lot est visible de tous : ses expériences dans un µprojet dont on n'est
pas membre n'y montrent que leur µprojet, leur statut et leurs dates - ni titre ni lien.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..accounts import service as accounts
from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as management
from ..areas.service import ManagementAreaNotFoundError, ThematicNotFoundError
from ..experiments.entities import compact
from ..experiments.lineage import lineage_graph
from ..experiments.repository import get_repository
from ..microprojects import service as microprojects
from ..wafers import service as plates
from . import service as lots
from .service import Lot, LotNotFoundError

router = APIRouter(prefix="/api/lots", tags=["lots"])


class CreateLotRequest(BaseModel):
    code: str | None = None  # vide = LOT-0001...
    title: str = ""
    description: str = ""
    priority: str = ""  # P10, P20...
    started_on: str | None = None
    forecast_exit_on: str | None = None
    wafers: list[str] = []
    thematic_ids: list[int] = []


class UpdateLotRequest(BaseModel):
    code: str
    title: str = ""
    description: str = ""
    priority: str = ""
    status: str
    started_on: str | None = None
    forecast_exit_on: str | None = None
    exited_on: str | None = None  # fin déclarée
    hold_reason: str = ""


class WafersRequest(BaseModel):
    lasermarks: list[str]


class ThematicsRequest(BaseModel):
    thematic_ids: list[int]


class _Context:
    """Ce qu'une requête relit pour tous ses lots une seule fois : l'index des plaques de tous les
    µprojets, les rôles de l'utilisateur, la filiation (dates, issue) de chaque µprojet concerné."""

    def __init__(self, user: User):
        self.user = user
        self.roles = {mp.id: role for mp, role in microprojects.list_for_user(user.id)}
        self._plates: dict[str, list[tuple[Any, dict]]] | None = None
        self._nodes: dict[str, dict[str, dict]] = {}
        self._thematics: dict[int, dict | None] = {}
        self._users: dict[int, str | None] = {}

    def plates_by_wafer(self) -> dict[str, list[tuple[Any, dict]]]:
        if self._plates is None:
            self._plates = {}
            for microproject in microprojects.list_all():
                for entry in plates.entries_for(microproject.slug):
                    key = compact(entry.get("sample_id"))
                    if key:
                        self._plates.setdefault(key, []).append((microproject, entry))
        return self._plates

    def node(self, slug: str, experiment_id: str) -> dict | None:
        """Le nœud de filiation de la pointe de la piste ``experiment_id``."""
        if slug not in self._nodes:
            graph = lineage_graph(get_repository(slug))
            self._nodes[slug] = {node["experiment_id"]: node for node in graph["nodes"] if node["is_tip"]}
        return self._nodes[slug].get(experiment_id)

    def thematic(self, thematic_id: int | None) -> dict | None:
        if thematic_id is None:
            return None
        if thematic_id not in self._thematics:
            try:
                thematic = management.get_thematic_by_id(thematic_id)
                area = management.get_by_id(thematic.management_area_id)
                self._thematics[thematic_id] = {
                    "id": thematic.id,
                    "slug": thematic.slug,
                    "name": thematic.name,
                    "area": {"slug": area.slug, "name": area.name},
                }
            except (ThematicNotFoundError, ManagementAreaNotFoundError):
                self._thematics[thematic_id] = None
        return self._thematics[thematic_id]

    def user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in self._users:
            found = accounts.get_by_id(user_id)
            self._users[user_id] = found.name if found else None
        return self._users[user_id]


def _get_lot(code: str) -> Lot:
    try:
        return lots.get_by_code(code)
    except LotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"lot « {code} » introuvable") from exc


def _days(a: str | None, b: str | None) -> int | None:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else None


def _schedule_payload(lot: Lot) -> dict:
    """Ce que les dates disent du lot : son retard (pas encore sorti, fin prévisionnelle dépassée),
    l'écart de sa fin déclarée sur la prévision (+ = en retard, - = en avance), ses durées."""
    today = date.today().isoformat()
    active = lot.status in lots.ACTIVE_STATUSES
    late = _days(lot.forecast_exit_on, today) if active and lot.forecast_exit_on and lot.forecast_exit_on < today else None
    return {
        "late_days": late,
        "exit_delta_days": _days(lot.forecast_exit_on, lot.exited_on),
        "planned_days": _days(lot.started_on, lot.forecast_exit_on),
        "elapsed_days": _days(lot.started_on, lot.exited_on or today) if lot.started_on and lot.started_on <= today else None,
    }


def _lot_payload(lot: Lot, ctx: _Context) -> dict:
    wafers = lots.list_wafers(lot.id)
    plates_by_wafer = ctx.plates_by_wafer()

    experiences: dict[tuple[str, str], dict] = {}
    wafer_rows = []
    for lasermark in wafers:
        used_in = []
        for microproject, entry in plates_by_wafer.get(compact(lasermark), []):
            member = microproject.id in ctx.roles
            exp = entry["experience"]
            key = (microproject.slug, exp["id"])
            node = ctx.node(microproject.slug, exp["id"])
            used_in.append(
                {
                    "microproject": microproject.code or microproject.name,
                    **({"id": exp["id"], "slug": microproject.slug, "title": exp["title"]} if member else {}),
                }
            )
            if key not in experiences:
                experiences[key] = {
                    "microproject": {
                        "slug": microproject.slug,
                        "code": microproject.code,
                        "name": microproject.name,
                        "thematic_id": microproject.thematic_id,
                    },
                    "member": member,
                    "status": node["status"] if node else exp["status"],
                    "decision": node["decision"] if node else None,
                    "started_at": node["started_at"] if node else exp["updated_at"],
                    "ended_at": node["ended_at"] if node else None,
                    "continued_at": node["continued_at"] if node else None,
                    "wafers": [],
                    **({"id": exp["id"], "title": exp["title"]} if member else {}),
                }
            if lasermark not in experiences[key]["wafers"]:
                experiences[key]["wafers"].append(lasermark)
        wafer_rows.append({"lasermark": lasermark, "experiences": used_in})

    thematics: dict[int, dict] = {}
    for thematic_id in lots.declared_thematic_ids(lot.id):
        found = ctx.thematic(thematic_id)
        if found:
            thematics[thematic_id] = {**found, "declared": True, "via_experiences": False}
    for experience in experiences.values():
        found = ctx.thematic(experience["microproject"].pop("thematic_id"))
        if found:
            thematics.setdefault(found["id"], {**found, "declared": False, "via_experiences": False})["via_experiences"] = True

    return {
        "code": lot.code,
        "title": lot.title,
        "description": lot.description,
        "priority": lot.priority,
        "status": lot.status,
        "source": lot.source,
        "started_on": lot.started_on,
        "forecast_exit_on": lot.forecast_exit_on,
        "exited_on": lot.exited_on,
        "hold_reason": lot.hold_reason,
        **_schedule_payload(lot),
        "wafers": wafer_rows,
        "experiences": sorted(experiences.values(), key=lambda e: e["started_at"] or ""),
        "thematiques": sorted(thematics.values(), key=lambda t: (t["area"]["name"], t["name"])),
        "created_by": ctx.user_name(lot.created_by),
        "created_at": lot.created_at,
        "updated_at": lot.updated_at,
        "can_delete": ctx.user.is_admin or lot.created_by == ctx.user.id,
    }


def _detail(lot: Lot, user: User) -> dict:
    return _lot_payload(lots.get_by_id(lot.id), _Context(user))


_FILTERS = {"actifs": lots.ACTIVE_STATUSES, "sortis": {"done"}, "annules": {"cancelled"}, "tous": None}


@router.get("")
def list_lots(statut: str = Query("actifs"), user: User = Depends(current_user)) -> dict:
    """Les lots à suivre (``actifs`` : en préparation, en cours ou en pause), ou ``sortis``,
    ``annules``, ``tous`` - par priorité (P10 d'abord), chacun avec ses dates, ses wafers, ses
    expériences et ses thématiques."""
    if statut not in _FILTERS:
        raise HTTPException(status_code=422, detail="statut doit être actifs, sortis, annules ou tous")
    ctx = _Context(user)
    return {
        "lots": [_lot_payload(lot, ctx) for lot in lots.list_all(_FILTERS[statut])],
        "today": date.today().isoformat(),
        "priorities": list(lots.PRIORITIES),
    }


@router.post("", status_code=201)
def create_lot(body: CreateLotRequest, user: User = Depends(current_user)) -> dict:
    try:
        lot = lots.create(
            code=body.code,
            title=body.title,
            description=body.description,
            priority=body.priority,
            started_on=body.started_on,
            forecast_exit_on=body.forecast_exit_on,
            wafers=body.wafers,
            thematic_ids=body.thematic_ids,
            created_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(lot, user)


@router.get("/recherche")
def search_lots(q: str = Query("", max_length=80), user: User = Depends(current_user)) -> list[dict]:
    """La topbar : les lots par code / intitulé, ou par un de leurs wafers (``wafer``)."""
    return [
        {"code": hit["lot"].code, "title": hit["lot"].title, "status": hit["lot"].status, "priority": hit["lot"].priority, "wafer": hit["wafer"]}
        for hit in lots.search(q)
    ]


@router.get("/selection")
def lot_choices(user: User = Depends(current_user)) -> list[dict]:
    """Les lots où l'on peut mettre un wafer, à tout moment : ceux pas encore sortis (P10 d'abord),
    puis ceux déjà sortis (les plus récents d'abord) - pas les annulés -, avec leurs wafers. Léger,
    pour le sélecteur « Ajouter au lot » d'un µprojet (graphe, fiche d'une expérience)."""
    done = sorted(lots.list_all({"done"}), key=lambda lot: lot.exited_on or "", reverse=True)
    return [
        {
            "code": lot.code,
            "title": lot.title,
            "priority": lot.priority,
            "status": lot.status,
            "forecast_exit_on": lot.forecast_exit_on,
            "wafers": lots.list_wafers(lot.id),
        }
        for lot in [*lots.list_all(lots.ACTIVE_STATUSES), *done]
    ]


@router.get("/thematiques")
def thematic_options(user: User = Depends(current_user)) -> list[dict]:
    """Toutes les thématiques, par projet corporate - pour déclarer celles qu'un lot vise."""
    options = []
    for area in management.list_all():
        thematics = management.list_thematics(area.id)
        if thematics:
            options.append({"area": {"slug": area.slug, "name": area.name}, "thematiques": [{"id": t.id, "name": t.name} for t in thematics]})
    return options


@router.get("/{code}")
def get_lot(code: str, user: User = Depends(current_user)) -> dict:
    return _detail(_get_lot(code), user)


@router.put("/{code}")
def update_lot(code: str, body: UpdateLotRequest, user: User = Depends(current_user)) -> dict:
    lot = _get_lot(code)
    try:
        lot = lots.update(lot.id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(lot, user)


@router.delete("/{code}")
def delete_lot(code: str, user: User = Depends(current_user)) -> dict:
    lot = _get_lot(code)
    if not (user.is_admin or lot.created_by == user.id):
        raise HTTPException(status_code=403, detail="seule la personne qui a créé le lot (ou un admin) peut le supprimer")
    lots.delete(lot.id)
    return {"deleted": lot.code}


@router.post("/{code}/wafers")
def add_wafers(code: str, body: WafersRequest, user: User = Depends(current_user)) -> dict:
    lot = _get_lot(code)
    try:
        lots.add_wafers(lot.id, body.lasermarks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(lot, user)


@router.delete("/{code}/wafers/{lasermark}")
def remove_wafer(code: str, lasermark: str, user: User = Depends(current_user)) -> dict:
    lot = _get_lot(code)
    lots.remove_wafer(lot.id, lasermark)
    return _detail(lot, user)


@router.put("/{code}/thematiques")
def set_thematics(code: str, body: ThematicsRequest, user: User = Depends(current_user)) -> dict:
    lot = _get_lot(code)
    try:
        lots.set_thematics(lot.id, body.thematic_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(lot, user)
