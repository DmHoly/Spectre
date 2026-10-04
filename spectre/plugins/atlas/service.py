"""The atlas of a corporate project: every microproject of that area the viewer belongs to, the lines
of study in each, the physical entities tracked on them and the links between them - one payload for
the client-side D3 force graph (``plugins/atlas/static/atlas.js``).

Nodes are lines of study (``experiment_id``, the piste), shown at their tip
(:func:`spectre.plugins.experiments.repository.branch_tips` - one per line, not every version ever
committed to it); :func:`spectre.plugins.experiments.lineage.condensed_edges` collapses the
intermediate commits between two tips down to a single edge, so forks and merges still show up
without drawing the whole history. An entity is addressed as the links address it (µprojet, piste,
index into the tip's ``physical_tracking``), so a link survives any write on either study.

Scoped to one area rather than every microproject of the company - the grouping the rest of the
app organizes around. Visibility is membership-based: this shows real experiment content (titles,
objectives, wafer identifiers), so only the area's microprojects the viewer belongs to are included,
and only the links whose both sides the viewer can see (:mod:`spectre.plugins.links.service`).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..accounts.service import User
from ..areas import service as areas
from ..experiments.entities import entities_for
from ..experiments.lineage import condensed_edges
from ..experiments.repository import branch_tips, display_status, get_repository
from ..links import service as links
from ..microprojects import service as microprojects


def objective_statuses(experiment: Any) -> list[dict]:
    """Each objective paired with its answer at conclude time, if any - the same lookup
    the fiche does client-side (``plugins/experiments/static/objectives.js``),
    computed here once so the atlas's node-click panel doesn't need a second round trip."""
    results_by_name = {result.objective: result for result in experiment.conclusion.objective_results}
    return [
        {"name": objective.name, "status": results_by_name[objective.name].status if objective.name in results_by_name else None}
        for objective in experiment.objectives
    ]


def _microproject_node(microproject: microprojects.Microproject, role: str) -> dict:
    repo = get_repository(microproject.slug)
    tips = branch_tips(repo)
    piste = {tip.id: tip.branch for tip in tips}
    return {
        "slug": microproject.slug,
        "name": microproject.name,
        "description": microproject.description,
        "role": role,
        "experiments": [
            {
                "experiment_id": tip.branch,
                "version_id": tip.id,
                "title": tip.title,
                "intent": tip.intent,
                "status": display_status(tip),
                "decision": tip.conclusion.decision,
                "conclusion_summary": tip.conclusion.summary,
                "objectives": objective_statuses(tip),
                "entities": entities_for(tip),
            }
            for tip in tips
        ],
        "edges": [{"from": piste[a], "to": piste[b]} for a, b in condensed_edges(repo, tips)],
    }


def atlas(area_slug: str, user: User) -> dict:
    area = areas.get_by_slug(area_slug)
    return {
        "area": {"slug": area.slug, "name": area.name},
        "microprojects": [
            _microproject_node(microproject, role)
            for microproject, role in microprojects.list_for_user(user.id)
            if microproject.management_area_id == area.id
        ],
        "microproject_links": [asdict(link) for link in links.list_microproject_links(user.id, area=area.slug)],
        "entity_links": [asdict(link) for link in links.list_entity_links(user.id, area=area.slug)],
    }
