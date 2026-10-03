"""Suivi de lots (``/api/lots``, domaine dans :mod:`.service`) : la liste (vue Gantt, ou résumée pour
un sélecteur ou des badges), la fiche d'un lot et sa saisie déclarative (priorité P10/P20..., début,
fin prévisionnelle, fin déclarée, wafers, thématiques visées).

Ce que la base ne stocke pas est déduit ici, à chaque lecture : les **expériences** d'un lot sont
les études (pointes de piste, comme l'index des plaques) qui suivent un de ses wafers - toutes,
même terminées avant que le wafer n'y entre -, et ses **thématiques** celles des µprojets de ces
études, plus les thématiques déclarées à la main. Un lot est visible de tous ; ses expériences le
sont selon la règle de visibilité des plaques (:mod:`spectre.plugins.wafers.service`) : dans un
µprojet dont on n'est pas membre, seulement leur µprojet, leur statut et leurs dates.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Response

from ...kernel.http import created, etag, if_match_version
from ..accounts import service as accounts
from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from ..experiments.lineage import lineage_graph
from ..experiments.repository import get_repository
from ..wafers import service as wafers
from . import service as lots
from .schemas import LotCreate, LotPatch, LotThematics, LotWafersAdd
from .service import Lot, LotWafer

router = APIRouter(prefix="/api", tags=["lots"])


class _Context:
    """Ce qu'une requête lit une seule fois pour tous ses lots : leurs wafers et leurs thématiques
    déclarées, les études qui suivent ces wafers (vues par l'utilisateur), la filiation (dates,
    issue) de chaque µprojet concerné, les thématiques, les auteurs."""

    def __init__(self, user: User, selected: list[Lot]):
        self.user = user
        ids = [lot.id for lot in selected]
        self.wafers = lots.wafers_of(ids)
        self.declared = lots.declared_thematic_ids(ids)
        self._occurrences: dict[str, list[wafers.Occurrence]] | None = None
        self._nodes: dict[str, dict[str, dict]] = {}
        self._thematics: dict[int, dict] | None = None
        self._users: dict[int, str | None] = {}

    def occurrences(self, key: str) -> list[wafers.Occurrence]:
        """Les études qui suivent le wafer ``key`` - lues une fois pour tous les wafers des lots."""
        if self._occurrences is None:
            keys = {wafer.key for found in self.wafers.values() for wafer in found}
            self._occurrences = {}
            for occurrence in wafers.occurrences(self.user.id, keys=keys) if keys else []:
                self._occurrences.setdefault(occurrence.key, []).append(occurrence)
        return self._occurrences.get(key, [])

    def node(self, slug: str, experiment_id: str) -> dict | None:
        """Le nœud de filiation de la pointe de la piste ``experiment_id``."""
        if slug not in self._nodes:
            graph = lineage_graph(get_repository(slug))
            self._nodes[slug] = {node["experiment_id"]: node for node in graph["nodes"] if node["is_tip"]}
        return self._nodes[slug].get(experiment_id)

    def thematic(self, thematic_id: int | None) -> dict | None:
        if self._thematics is None:
            by_area = {area.id: area for area in areas.list_all()}
            self._thematics = {
                t.id: {"id": t.id, "slug": t.slug, "name": t.name, "area": {"slug": by_area[t.management_area_id].slug, "name": by_area[t.management_area_id].name}}
                for t in areas.list_thematics()
                if t.management_area_id in by_area
            }
        return self._thematics.get(thematic_id) if thematic_id is not None else None

    def user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        if user_id not in self._users:
            found = accounts.get_by_id(user_id)
            self._users[user_id] = found.name if found else None
        return self._users[user_id]


def _days(a: str | None, b: str | None) -> int | None:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else None


def _schedule_payload(lot: Lot) -> dict:
    """Ce que les dates disent du lot : son retard (pas encore sorti, fin prévisionnelle dépassée),
    l'écart de sa fin déclarée sur la prévision (+ = en retard, - = en avance), ses durées."""
    today = date.today().isoformat()
    late = _days(lot.forecast_exit_on, today) if lot.is_active and lot.forecast_exit_on and lot.forecast_exit_on < today else None
    return {
        "late_days": late,
        "exit_delta_days": _days(lot.forecast_exit_on, lot.exited_on),
        "planned_days": _days(lot.started_on, lot.forecast_exit_on),
        "elapsed_days": _days(lot.started_on, lot.exited_on or today) if lot.started_on and lot.started_on <= today else None,
    }


def _wafer_ref(wafer: LotWafer) -> dict:
    return {"key": wafer.key, "lasermark": wafer.lasermark}


def _summary_payload(lot: Lot, ctx: _Context) -> dict:
    """Un lot en bref : pour un sélecteur, ou les badges d'une plaque ou d'un graphe."""
    return {
        "id": lot.id,
        "code": lot.code,
        "title": lot.title,
        "priority": lot.priority,
        "status": lot.status,
        "is_active": lot.is_active,
        "source": lot.source,
        "forecast_exit_on": lot.forecast_exit_on,
        "exited_on": lot.exited_on,
        "wafers": [_wafer_ref(wafer) for wafer in ctx.wafers[lot.id]],
    }


def _lot_payload(lot: Lot, ctx: _Context) -> dict:
    experiments: dict[tuple[str, str], dict] = {}
    thematics: dict[int, dict] = {}
    wafer_rows = []
    for wafer in ctx.wafers[lot.id]:
        used_in = []
        for occurrence in ctx.occurrences(wafer.key):
            used_in.append(wafers.experiment_payload(occurrence, {}))
            key = (occurrence.microproject.slug, occurrence.experiment_id)
            if key not in experiments:
                node = ctx.node(*key) or {}
                experiments[key] = wafers.experiment_payload(
                    occurrence,
                    {
                        "status": node.get("status", occurrence.entry["experiment"]["status"]),
                        "decision": node.get("decision"),
                        "started_at": node.get("started_at", occurrence.updated_at),
                        "ended_at": node.get("ended_at"),
                        "continued_at": node.get("continued_at"),
                        "wafers": [],
                    },
                )
                found = ctx.thematic(occurrence.microproject.thematic_id)
                if found:
                    thematics.setdefault(found["id"], {**found, "declared": False, "via_experiments": False})["via_experiments"] = True
            if wafer.lasermark not in experiments[key]["wafers"]:
                experiments[key]["wafers"].append(wafer.lasermark)
        wafer_rows.append({**_wafer_ref(wafer), "experiments": used_in})

    for thematic_id in ctx.declared[lot.id]:
        found = ctx.thematic(thematic_id)
        if found:
            thematics.setdefault(found["id"], {**found, "declared": False, "via_experiments": False})["declared"] = True

    return {
        **_summary_payload(lot, ctx),
        "description": lot.description,
        "started_on": lot.started_on,
        "hold_reason": lot.hold_reason,
        **_schedule_payload(lot),
        "wafers": wafer_rows,
        "experiments": sorted(experiments.values(), key=lambda e: e["started_at"] or ""),
        "thematics": sorted(thematics.values(), key=lambda t: (t["area"]["name"], t["name"])),
        "created_by": ctx.user_name(lot.created_by),
        "created_at": lot.created_at,
        "updated_at": lot.updated_at,
        "can_delete": lots.can_delete(lot, ctx.user.id, ctx.user.is_admin),
    }


def _respond(response: Response, lot: Lot, user: User) -> dict:
    """Le lot entier, avec sa version en ``ETag`` (à renvoyer en ``If-Match`` pour le modifier)."""
    response.headers["ETag"] = etag(lot.updated_at)
    return _lot_payload(lot, _Context(user, [lot]))


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@router.get("/lots")
def list_lots(
    status: str = "",
    q: str = Query("", max_length=80),
    wafer: str = "",
    code: str | None = None,
    view: Literal["full", "summary"] = "full",
    user: User = Depends(current_user),
) -> list[dict]:
    """Les lots par priorité (P10 d'abord) - ou, avec ``q``, par pertinence (code, intitulé, wafer).
    ``status`` : des statuts séparés par des virgules (tous par défaut) ; ``wafer`` : des clés de
    wafer séparées par des virgules (les lots qui contiennent l'une d'elles) ; ``code`` : le code
    exact (sans la casse) ; ``view=summary`` : sans expériences ni thématiques."""
    statuses = lots.check_statuses(_csv(status)) or None
    filters: dict[str, Any] = {"statuses": statuses, "code": code}
    if wafer:
        filters["wafer_keys"] = _csv(wafer)
    if q.strip():
        selected = [lot for lot, _wafer in lots.search(q, statuses=statuses)]
        if wafer or code is not None:
            kept = {lot.id for lot in lots.list_lots(**filters)}
            selected = [lot for lot in selected if lot.id in kept]
    else:
        selected = lots.list_lots(**filters)
    ctx = _Context(user, selected)
    payload = _summary_payload if view == "summary" else _lot_payload
    return [payload(lot, ctx) for lot in selected]


@router.get("/lot-priorities")
def list_priorities(user: User = Depends(current_user)) -> list[str]:
    """Les priorités proposées à la saisie (toute valeur courte est acceptée)."""
    return list(lots.PRIORITIES)


@router.post("/lots", status_code=201)
def create_lot(body: LotCreate, response: Response, user: User = Depends(current_user)) -> dict:
    lot = lots.create(**body.model_dump(), created_by=user.id)
    created(response, f"/api/lots/{lot.id}")
    return _respond(response, lot, user)


@router.get("/lots/{lot_id}")
def get_lot(lot_id: int, response: Response, user: User = Depends(current_user)) -> dict:
    return _respond(response, lots.get(lot_id), user)


@router.patch("/lots/{lot_id}")
def update_lot(lot_id: int, body: LotPatch, response: Response, if_match: str | None = Header(None), user: User = Depends(current_user)) -> dict:
    """Les champs envoyés seulement ; ``If-Match`` : la version affichée (``updated_at``), sinon 412."""
    lot = lots.update(lot_id, body.model_dump(exclude_unset=True), expected_version=if_match_version(if_match))
    return _respond(response, lot, user)


@router.delete("/lots/{lot_id}", status_code=204)
def delete_lot(lot_id: int, user: User = Depends(current_user)) -> Response:
    lots.delete(lot_id, user_id=user.id, is_admin=user.is_admin)
    return Response(status_code=204)


@router.post("/lots/{lot_id}/wafers", status_code=201)
def add_wafers(lot_id: int, body: LotWafersAdd, response: Response, user: User = Depends(current_user)) -> dict:
    """Ajoute des wafers au lot : 201 et le lot ; 200 si tous y étaient déjà (rien n'est écrit).
    Sans ``Location`` : un wafer d'un lot n'a pas de route propre, il se lit dans le lot."""
    if not lots.add_wafers(lot_id, body.lasermarks):
        response.status_code = 200
    return _respond(response, lots.get(lot_id), user)


@router.delete("/lots/{lot_id}/wafers/{wafer_key}", status_code=204)
def remove_wafer(lot_id: int, wafer_key: str, user: User = Depends(current_user)) -> Response:
    lots.remove_wafer(lot_id, wafer_key)
    return Response(status_code=204)


@router.put("/lots/{lot_id}/thematics")
def set_thematics(lot_id: int, body: LotThematics, response: Response, user: User = Depends(current_user)) -> dict:
    """Les thématiques déclarées « visées » (ids de ``GET /api/thematics``), remplacées en bloc."""
    lots.set_thematics(lot_id, body.thematic_ids)
    return _respond(response, lots.get(lot_id), user)
