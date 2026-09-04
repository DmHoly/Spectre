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
    don't get a point, there'd be nothing to show or label. ``index`` is the entry's position in
    the *raw* ``physical_tracking`` list, not in this (filtered, so potentially shorter) returned
    one - the addressing :mod:`spectre.core.links` and attachments both use, so it has to survive
    a campaign with some variants tracked and others still blank rather than silently compacting
    and pointing a link/attachment at the wrong sample.
    """
    return [
        {"index": i, "sample_id": entry.get("sample_id"), "location": entry.get("location")}
        for i, entry in enumerate(experiment.metadata.get("physical_tracking", []))
        if entry.get("sample_id") or entry.get("location")
    ]


def entity_history_for_project(repo: Any, tips: list[Any]) -> dict[str, list[str]]:
    """Every distinct sample_id/location already used anywhere on the project's current branch
    tips - not the full commit history (a superseded intermediate version's entities don't
    surface), the same "current state, not every version" scope :func:`entities_for` already
    works at. Meant to feed an autocomplete on the physical-entities editor so a user typing a
    sample id or location sees what's already in use elsewhere in the project, rather than
    re-typing a slightly different spelling of the same thing.
    """
    sample_ids: set[str] = set()
    locations: set[str] = set()
    for tip in tips:
        for entry in entities_for(tip):
            if entry["sample_id"]:
                sample_ids.add(entry["sample_id"])
            if entry["location"]:
                locations.add(entry["location"])
    return {"sample_ids": sorted(sample_ids), "locations": sorted(locations)}


def objective_statuses(experiment: Any) -> list[dict]:
    """Each objective paired with its answer at conclude time, if any - the same lookup
    ``objectiveResultFor`` does client-side on the fiche (:mod:`spectre.api.static.js.experience`),
    computed here once so the atlas's node-click panel doesn't need a second round trip."""
    results_by_name = {result.objective: result for result in experiment.conclusion.objective_results}
    return [
        {"name": objective.name, "status": results_by_name[objective.name].status if objective.name in results_by_name else None}
        for objective in experiment.objectives
    ]


def attachments_for(experiment: Any) -> list[dict]:
    """Files uploaded on this experience (spectre.api.experiments's pieces-jointes routes) -
    ``entity_index`` is ``None`` for one attached to the study as a whole, or an index into this
    same tip's :func:`entities_for` list for one attached to a specific physical entity."""
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
