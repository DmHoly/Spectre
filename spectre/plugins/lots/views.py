"""Ce qu'une lecture de lots compose, sans HTTP : ce que la base ne stocke pas est déduit ici, à
chaque lecture. Les **expériences** d'un lot sont les études (pointes de piste, comme l'index des
plaques) qui suivent un de ses wafers - toutes, même terminées avant que le wafer n'y entre -, et ses
**thématiques** celles des µprojets de ces études, plus les thématiques déclarées à la main. Un lot
est visible de tous ; ses expériences le sont selon la règle de visibilité des plaques
(:mod:`spectre.plugins.wafers.service`) : dans un µprojet dont on n'est pas membre, seulement leur
µprojet, leur statut et leurs dates.

- :class:`Context` : ce qu'une requête lit une seule fois pour tous ses lots ;
- :func:`summary_payload` (sélecteur, badges) et :func:`lot_payload` (la fiche).
"""

from __future__ import annotations

from datetime import date

from ..accounts import service as accounts
from ..accounts.service import User
from ..areas import service as areas
from ..experiments.lineage import lineage_graph
from ..experiments.repository import get_repository
from ..wafers import service as wafers
from . import service as lots
from .service import Lot, LotWafer


class Context:
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


def summary_payload(lot: Lot, ctx: Context) -> dict:
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


def lot_payload(lot: Lot, ctx: Context) -> dict:
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
        **summary_payload(lot, ctx),
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
