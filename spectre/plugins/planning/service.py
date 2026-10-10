"""Le planning d'une équipe : toutes les plaques de ses études, rangées par thématique ▸ µprojet ▸
étude (une épi), avec les lots qu'elles portent - en cours, sortis ou **prévus** - et les
expériences prévisionnelles de ses µprojets. De quoi suivre la logique d'une équipe et préparer ses
prochains lots.

Ce plugin ne stocke rien : un lot prévu est un lot du plugin ``lots`` au statut ``planned``,
créé et rempli par ses routes ; une expérience prévue est celle de l'arbre d'un µprojet
(``experiments.plans``). Il compose seulement une lecture qui traverse les µprojets d'une équipe
(ARCHITECTURE.md § 3 : une agrégation vit dans le plugin le plus haut qui en possède les données).

**Qui le lit** : un manager de l'équipe (owner de ses µprojets, il voit tout) ou un administrateur.
Une équipe est celle des projets corporate qui lui sont rattachés (``management_areas.team_id``),
leurs µprojets en sont les sujets ; les thématiques les rangent (« Sans thématique » sinon).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...kernel.errors import Forbidden
from ..accounts.service import User
from ..areas import service as areas
from ..experiments import plans
from ..experiments.lineage import lineage_graph
from ..experiments.repository import branch_tips, get_repository
from ..lots import service as lots
from ..microprojects import service as microprojects
from ..structures import kinds
from ..teams import service as teams
from ..teams.service import Team
from ..wafers.service import wafer_key


def teams_for(user: User) -> list[Team]:
    """Les équipes dont ``user`` peut lire le planning : celles qu'il manage, toutes pour un admin."""
    found = teams.list_all()
    if user.is_admin:
        return found
    managed = teams.managed_team_ids(user.id)
    return [team for team in found if team.id in managed]


def _team(user: User, team_slug: str | None) -> Team | None:
    """L'équipe demandée (la première lisible sans ``team_slug``) - 404 si elle n'existe pas, 403
    si ``user`` n'en est pas manager."""
    readable = teams_for(user)
    if not team_slug:
        return readable[0] if readable else None
    team = teams.get_by_slug(team_slug)
    if team.id not in {t.id for t in readable}:
        raise Forbidden("Le planning d'une équipe est réservé à ses managers.", code="planning_forbidden")
    return team


def _wafer_rows(tip: Any) -> list[dict]:
    """Les places de l'étude ``tip`` : une par plaque suivie, à associer comprise (sans lasermark)."""
    labels = tip.metadata.get("campaign_labels") or []
    rows = []
    for index, entry in enumerate(tip.metadata.get("physical_tracking", [])):
        lasermark = entry.get("sample_id") or None
        rows.append(
            {
                "index": index,
                "lasermark": lasermark,
                "key": wafer_key(lasermark) if lasermark else None,
                "variant": labels[index] if index < len(labels) else None,
                "fdl": list(entry.get("fdl") or []),
                "location": entry.get("location"),
            }
        )
    return rows


def _studies(slug: str) -> list[dict]:
    """Les études (une par piste, sa pointe) du µprojet ``slug``, de la plus ancienne à la plus
    récente, chacune avec ses dates (celles de la filiation : début de la piste, fin à sa
    conclusion) et ses plaques."""
    repo = get_repository(slug)
    nodes = lineage_graph(repo)["nodes"]
    started: dict[str, str] = {}
    for node in nodes:
        line = node["experiment_id"]
        if line not in started or node["started_at"] < started[line]:
            started[line] = node["started_at"]
    tip_nodes = {node["experiment_id"]: node for node in nodes if node["is_tip"]}
    studies = []
    for tip in branch_tips(repo):
        node = tip_nodes.get(tip.branch, {})
        studies.append(
            {
                "id": tip.branch,
                "version_id": tip.id,
                "title": tip.title,
                "intent": tip.intent,
                "status": node.get("status") or tip.conclusion.status,
                "decision": tip.conclusion.decision,
                "started_at": started.get(tip.branch) or tip.created_at.isoformat(),
                "ended_at": node.get("ended_at"),
                "updated_at": tip.created_at.isoformat(),
                "campaign": tip.structure_type == kinds.ProcessLot.registry_key(),
                "url": f"/microprojets/{slug}/experiences/{tip.branch}",
                "wafers": _wafer_rows(tip),
            }
        )
    return sorted(studies, key=lambda s: s["started_at"])


def _plan_row(slug: str, plan: plans.Plan) -> dict:
    count = len(plan.wafers) if plan.mode == "same_wafers" else (plan.wafer_count or 0)
    return {
        "id": plan.id,
        "title": plan.title,
        "intent": plan.intent,
        "mode": plan.mode,
        "wafers": list(plan.wafers),
        "wafer_count": count,
        "created_at": plan.created_at,
        "url": f"/microprojets/{slug}",  # l'arbre du µprojet, où la prévision se lance
    }


def _lot_row(lot: lots.Lot, wafer_keys: list[str]) -> dict:
    return {
        "id": lot.id,
        "code": lot.code,
        "title": lot.title,
        "priority": lot.priority,
        "status": lot.status,
        "started_on": lot.started_on,
        "forecast_exit_on": lot.forecast_exit_on,
        "exited_on": lot.exited_on,
        "hold_reason": lot.hold_reason,
        "source": lot.source,
        "updated_at": lot.updated_at,
        "url": f"/lots/{lot.code}",
        "wafers": wafer_keys,
    }


def board(user: User, *, team_slug: str | None = None) -> dict:
    """Le planning de l'équipe ``team_slug`` (la première que ``user`` manage sans elle) :

    - ``teams`` : les équipes dont ``user`` peut lire le planning (le sélecteur), ``team`` celle-ci
      (``None`` s'il n'en manage aucune) ;
    - ``groups`` : par thématique (projet par projet, dans leur ordre ; ``thematic`` à ``None`` pour
      les µprojets du projet qui n'en ont pas), ses µprojets, chacun avec ses ``studies`` (et leurs
      ``wafers``) et ses ``plans`` (expériences prévues, pas encore lancées) ;
    - ``lots`` : chaque lot qui porte au moins une plaque de ces études, avec les clés de ses
      plaques (``wafers``) - un lot prévu est au statut ``planned`` ;
    - ``today`` : la date du serveur, pour la frise.
    """
    readable = teams_for(user)
    team = _team(user, team_slug)
    payload: dict[str, Any] = {
        "teams": [{"slug": t.slug, "name": t.name} for t in readable],
        "team": {"slug": team.slug, "name": team.name} if team else None,
        "today": date.today().isoformat(),
        "areas": [],
        "groups": [],
        "lots": [],
    }
    if team is None:
        return payload

    team_areas = areas.list_all(team_id=team.id)
    payload["areas"] = [{"slug": a.slug, "name": a.name} for a in team_areas]
    area_ids = {a.id for a in team_areas}
    selected = sorted(
        (m for m in microprojects.list_all() if m.management_area_id in area_ids), key=lambda m: (m.code or "", m.name.casefold())
    )

    groups: list[dict] = []
    by_thematic: dict[tuple[int, int | None], dict] = {}
    for area in team_areas:
        for thematic in areas.list_thematics(area.id):
            group = {"area": {"slug": area.slug, "name": area.name}, "thematic": {"id": thematic.id, "slug": thematic.slug, "name": thematic.name}, "microprojects": []}
            by_thematic[(area.id, thematic.id)] = group
            groups.append(group)
        loose = {"area": {"slug": area.slug, "name": area.name}, "thematic": None, "microprojects": []}
        by_thematic[(area.id, None)] = loose
        groups.append(loose)

    keys: set[str] = set()
    for mp in selected:
        studies = _studies(mp.slug)
        keys.update(w["key"] for s in studies for w in s["wafers"] if w["key"])
        group = by_thematic.get((mp.management_area_id, mp.thematic_id)) or by_thematic[(mp.management_area_id, None)]
        group["microprojects"].append(
            {
                "slug": mp.slug,
                "code": mp.code,
                "name": mp.name,
                "url": f"/microprojets/{mp.slug}",
                "studies": studies,
                "plans": [_plan_row(mp.slug, plan) for plan in plans.list_plans(mp.id)],
            }
        )
    payload["groups"] = [g for g in groups if g["microprojects"]]

    if keys:
        found = lots.list_lots(wafer_keys=keys)
        wafers_by_lot = lots.wafers_of([lot.id for lot in found])
        payload["lots"] = [_lot_row(lot, [w.key for w in wafers_by_lot.get(lot.id, [])]) for lot in found]
    return payload
