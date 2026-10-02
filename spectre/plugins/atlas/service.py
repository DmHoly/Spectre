"""The cross-microproject atlas: a bird's-eye view spanning every microproject a user belongs to, rather
than the per-microproject lineage. Nodes here are branch tips
(:func:`spectre.plugins.experiments.repository.branch_tips` - one per line of study, not every
version ever committed to it) and the physical entities tracked on them
(:func:`spectre.plugins.experiments.entities.entities_for`);
:func:`spectre.plugins.experiments.lineage.condensed_edges` collapses the intermediate commits
between two tips down to a single link, so forks and merges still show up without drawing the whole
history.
"""

from __future__ import annotations

from typing import Any


def objective_statuses(experiment: Any) -> list[dict]:
    """Each objective paired with its answer at conclude time, if any - the same lookup
    ``objectiveResultFor`` does client-side on the fiche (``static/js/experience.js``),
    computed here once so the atlas's node-click panel doesn't need a second round trip."""
    results_by_name = {result.objective: result for result in experiment.conclusion.objective_results}
    return [
        {"name": objective.name, "status": results_by_name[objective.name].status if objective.name in results_by_name else None}
        for objective in experiment.objectives
    ]


def attachments_for(experiment: Any) -> list[dict]:
    """Files uploaded on this experience (spectre.plugins.experiments.api's pieces-jointes routes) -
    ``entity_index`` is ``None`` for one attached to the study as a whole, or an index into this
    same tip's :func:`~spectre.plugins.experiments.entities.entities_for` list for one attached to a
    specific physical entity."""
    return [
        {
            "id": a["id"],
            "filename": a["filename"],
            "content_type": a["content_type"],
            "size": a["size"],
            "entity_index": a.get("entity_index"),
        }
        for a in experiment.metadata.get("attachments", [])
    ]
