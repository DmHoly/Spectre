"""An experiment lineage, read two ways: the µprojet's structural graph (:func:`lineage_graph` -
one node per structurally distinct version, Follow's commit chain collapsed by
:mod:`spectre.plugins.experiments.versioning`), and the condensed edges between a chosen set of
versions (:func:`condensed_edges` - branch tips for the atlas, refs for the refs page).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import versioning
from .entities import compact
from .repository import CONCLUDED_STATUSES, display_status, hold_of


def lineage_graph(repo: Any) -> dict:
    """The ``{"nodes", "edges"}`` payload of the µprojet's lineage (``GET .../lineage``, see
    :func:`spectre.plugins.experiments.api.microproject_lineage` for what each node means) for one
    repository - shared with the frise of a thématique (:mod:`spectre.plugins.experiments.insights`),
    which lays out the same nodes on a time axis, and with the lots (:mod:`spectre.plugins.lots.api`).
    Each node is a version (``version_id``, also its ``id`` in ``edges``) of a line of study
    (``experiment_id``), the line's tip or not (``is_tip``). The lots holding a node's wafers are
    the lots plugin's own (``GET /api/lots?wafer=``) : the page composes their badges."""
    experiments = {exp.id: exp for exp in repo}
    if not experiments:
        return {"nodes": [], "edges": []}

    dag = {exp_id: exp.parents for exp_id, exp in experiments.items()}
    processes = {exp_id: versioning.structure_signature(exp.metadata) for exp_id, exp in experiments.items()}
    tips = set(repo.branches.values())
    structural_ids = versioning.determine_keep_ids(dag, processes, tips=set())
    collapsed = versioning.collapsed_dag(dag, structural_ids)

    def nearest_structural_ancestor(exp_id: str) -> str:
        while exp_id not in structural_ids:
            parents = dag[exp_id]
            if len(parents) != 1:
                return exp_id  # unreachable in practice - a merge is always its own structural id
            exp_id = parents[0]
        return exp_id

    tips_by_anchor: dict[str, list[str]] = {}
    for tip_id in tips:
        if tip_id not in structural_ids:
            tips_by_anchor.setdefault(nearest_structural_ancestor(tip_id), []).append(tip_id)

    def line_start(exp_id: str, anchor_id: str) -> datetime:
        """When the line ending at tip ``exp_id`` started, for two tips forked off the same
        structural point ``anchor_id``: its first commit after that point."""
        start = experiments[exp_id].created_at
        parents = dag[exp_id]
        while len(parents) == 1 and parents[0] != anchor_id:
            exp_id = parents[0]
            start = experiments[exp_id].created_at
            parents = dag[exp_id]
        return start

    def node_payload(exp_id: str, *, is_tip: bool, is_merge_id: str, started_at: datetime) -> dict:
        exp = experiments[exp_id]
        ended_at = None
        if exp.conclusion.status in CONCLUDED_STATUSES:
            ended_at = exp.conclusion.decided_at or exp.created_at
        hold = hold_of(exp)
        return {
            "id": exp_id,  # the node, in "edges"
            "version_id": exp_id,
            "experiment_id": exp.branch,
            "title": exp.title,
            "status": display_status(exp),
            "hold": {"since": hold.get("since"), "reason": hold.get("reason")} if hold else None,
            "decision": exp.conclusion.decision,
            "author": exp.author,
            "created_at": exp.created_at.isoformat(),
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat() if ended_at else None,
            "conclusion_summary": exp.conclusion.summary,
            "is_merge": len(dag[is_merge_id]) > 1,
            "is_tip": is_tip,
        }

    # A structural id's own commit isn't always what ends up in ``nodes`` for it (the common-case
    # override below shows a live tip instead) - every edge from ``collapsed`` must be translated
    # through this before use, or it points at an id no node in the response actually carries.
    display_id: dict[str, str] = {}
    nodes = []
    for exp_id in structural_ids:
        resolved_tips = tips_by_anchor.get(exp_id, [])
        already_a_tip = exp_id in tips
        started_at = experiments[exp_id].created_at
        if not already_a_tip and len(resolved_tips) == 1:
            display_id[exp_id] = resolved_tips[0]
            nodes.append(node_payload(resolved_tips[0], is_tip=True, is_merge_id=exp_id, started_at=started_at))
        else:
            display_id[exp_id] = exp_id
            nodes.append(node_payload(exp_id, is_tip=already_a_tip, is_merge_id=exp_id, started_at=started_at))
            for tip_id in resolved_tips:  # only non-empty when ambiguous (len > 1) - see docstring
                nodes.append(
                    node_payload(tip_id, is_tip=True, is_merge_id=exp_id, started_at=line_start(tip_id, exp_id))
                )

    edges = [
        {"parent": display_id[parent], "child": display_id[child]}
        for child, parents in collapsed.items()
        for parent in parents
    ]
    for exp_id, resolved_tips in tips_by_anchor.items():
        if len(resolved_tips) > 1:
            edges.extend({"parent": display_id[exp_id], "child": tip_id} for tip_id in resolved_tips)

    # When the work moved on from a node: its first child's start - what ends the elapsed time of a
    # draft that was never concluded but continued into a new version (« poursuivie »). And the
    # wafers it tracks - the badge beside its node.
    started = {node["id"]: node["started_at"] for node in nodes}
    for node in nodes:
        children = [started[edge["child"]] for edge in edges if edge["parent"] == node["id"]]
        node["continued_at"] = min(children) if children else None
        if node["continued_at"]:
            node["status"] = display_status(experiments[node["id"]], continued=True)
        tracked = [e.get("sample_id") for e in experiments[node["id"]].metadata.get("physical_tracking", []) if e.get("sample_id")]
        # ses wafers (sans doublon, même règle que l'index des plaques) : le badge à gauche du nœud
        seen: set[str] = set()
        node["wafers"] = []
        for lasermark in tracked:
            if compact(lasermark) not in seen:
                seen.add(compact(lasermark))
                node["wafers"].append(lasermark)

    return {"nodes": nodes, "edges": edges}


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
