"""The cross-project atlas: a bird's-eye view spanning every project a user belongs to, rather
than the per-project "vue d'ensemble" (:mod:`spectre.api.experiments`'s ``project_graph_html``,
which plots full commit history one node per version). Nodes here are branch tips
(:func:`spectre.core.projects.branch_tips` - one per line of study, not every version ever
committed to it) and the physical entities tracked on them; :func:`condensed_edges` collapses the
intermediate commits between two tips down to a single link, so forks and merges still show up
without drawing the whole history.
"""

from __future__ import annotations

from typing import Any


def condensed_edges(repo: Any, tips: list[Any]) -> list[tuple[str, str]]:
    """One ``(ancestor_tip_id, tip_id)`` pair per path from a tip back to the nearest ancestor
    that is itself a current branch tip - a plain evolution yields one edge, a merge (two
    parents) yields two, and a tip with no tip ancestor (the start of a fresh line of study, or
    everything upstream of it since superseded) yields none. Walks ``.parents`` rather than
    ``repo.log()`` deliberately: ``log()`` follows one line at a time, and a merge commit's second
    parent needs following too for its own path to surface as a separate edge.
    """
    tip_ids = {tip.id for tip in tips}
    edges: set[tuple[str, str]] = set()
    for tip in tips:
        frontier = list(tip.parents)
        seen = set(frontier)
        while frontier:
            candidate_id = frontier.pop()
            if candidate_id in tip_ids:
                edges.add((candidate_id, tip.id))
                continue
            candidate = repo.get(candidate_id)
            for grandparent_id in candidate.parents:
                if grandparent_id not in seen:
                    seen.add(grandparent_id)
                    frontier.append(grandparent_id)
    return sorted(edges)


def entities_for(experiment: Any) -> list[dict]:
    """The physical entities worth showing as their own atlas node - entries that carry no
    ``sample_id``/``location`` at all (the common case: most experiments never fill this in)
    don't get a point, there'd be nothing to show or label."""
    return [
        {"sample_id": entry.get("sample_id"), "location": entry.get("location")}
        for entry in experiment.metadata.get("physical_tracking", [])
        if entry.get("sample_id") or entry.get("location")
    ]


def objective_statuses(experiment: Any) -> list[dict]:
    """Each objective paired with its answer at conclude time, if any - the same lookup
    ``objectiveResultFor`` does client-side on the fiche (:mod:`spectre.api.static.js.experience`),
    computed here once so the atlas's node-click panel doesn't need a second round trip."""
    results_by_name = {result.objective: result for result in experiment.conclusion.objective_results}
    return [
        {"name": objective.name, "status": results_by_name[objective.name].status if objective.name in results_by_name else None}
        for objective in experiment.objectives
    ]
