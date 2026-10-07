"""An experiment lineage, read three ways: the µprojet's structural graph (:func:`lineage_graph` -
one node per structurally distinct version, Follow's commit chain collapsed by
:mod:`spectre.plugins.experiments.versioning`), the history of its structures, line by line
(:func:`structure_history` - the « Évolution des structures » page), and the condensed edges
between a chosen set of versions (:func:`condensed_edges` - branch tips for the atlas, refs).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..structures import kinds
from . import versioning
from .entities import compact, study_fdl
from .repository import CONCLUDED_STATUSES, display_status, hold_of

# Ce que montre l'historique des structures par défaut : les versions qui changent la structure en
# grand (la première, un changement majeur ou mineur) ; un correctif (un nom d'étape) ou une version
# sans changement de structure (une étiquette, une preuve...) est « légère ».
STRUCTURAL_LEVELS = ("initial", "major", "minor")


def _structure_kind(structure_type: str) -> str:
    """« process », « campaign » ou « images » : ce que l'éditeur ouvre pour partir de la version."""
    kind = kinds.KINDS.get(structure_type)
    return "images" if kind is kinds.IMAGES else "campaign" if kind is kinds.CAMPAIGN else "process"


def structure_history(repo: Any, *, all_versions: bool = False, include: set[str] | None = None) -> dict:
    """``{lanes, nodes, edges}`` : the µprojet's versions laid out line by line, for the
    « Évolution des structures » page - everything it draws, so the page computes nothing.

    - ``lanes``: one per line of study (the Follow branch a version was recorded on), in a stable
      order - when the line started (its first version), then its name -, so a new line always
      comes last. ``is_active`` is false for a deleted line whose first versions remain (another
      line forked from them); ``tip_version_id`` / ``tip_label`` say where an active line stands.
    - ``nodes``: by default the structural versions (:data:`STRUCTURAL_LEVELS`), the versions a ref
      points at, the merges and the first version of each line (a fork shows even before its
      structure changes); ``all_versions`` adds the light ones, ``include`` only those of these ids
      (the versions published as a reference, which the page reads from the references plugin -
      an unknown id is ignored). Each node carries its X.Y.Z
      (:func:`versioning.compute_branch_versions`, along its own first-parent history), its
      ``change_level``, its refs, its ``lane`` (index into ``lanes``) and ``experiment_id``, the
      line through which it can be opened (its own, or one whose history contains it).
    - ``edges``: ``{parent, child, kind}`` between shown nodes, through the hidden ones
      (:func:`versioning.collapsed_dag`) ; ``kind`` is ``parent`` (same line), ``fork`` (a line
      starting from another) or ``merge`` - into a merge, from each parent on another line: both
      parents of a combination (a new line made of two studies), the second parent of a merge
      recorded on its first parent's line (before combinations made a new line).
    """
    experiments = {exp.id: exp for exp in repo}
    if not experiments:
        return {"lanes": [], "nodes": [], "edges": []}
    dag = {exp_id: list(exp.parents) for exp_id, exp in experiments.items()}
    branches = repo.branches

    numbers: dict[str, dict[str, Any]] = {}
    containing: dict[str, set[str]] = {}
    for name in sorted(branches):
        history = list(reversed(repo.log(branches[name])))
        if branches[name] not in numbers:
            numbers.update(versioning.compute_branch_versions(history))
        for version in history:
            containing.setdefault(version.id, set()).add(name)
    for exp_id in experiments:  # reachable from no line by its first parents (a merged-in side)
        if exp_id not in numbers:
            numbers.update(versioning.compute_branch_versions(list(reversed(repo.log(exp_id)))))

    def line_of(exp: Any) -> str:
        lines = containing.get(exp.id, set())
        return exp.branch if exp.branch in lines or not lines else min(lines)

    lane_starts = {
        exp_id for exp_id, exp in experiments.items() if not exp.parents or experiments[exp.parents[0]].branch != exp.branch
    }
    ref_names: dict[str, list[str]] = {}
    for name, target in repo.tags.items():
        ref_names.setdefault(target, []).append(name)

    if all_versions:
        keep = set(experiments)
    else:
        keep = {
            exp_id
            for exp_id in experiments
            if numbers[exp_id]["level"] in STRUCTURAL_LEVELS
            or exp_id in ref_names
            or len(dag[exp_id]) != 1
            or exp_id in lane_starts
            or exp_id in (include or ())
        }

    by_lane: dict[str, list[Any]] = {}
    for exp in experiments.values():
        by_lane.setdefault(exp.branch, []).append(exp)
    lane_names = sorted(by_lane, key=lambda name: (min(exp.created_at for exp in by_lane[name]), name))
    lane_index = {name: i for i, name in enumerate(lane_names)}
    lanes = []
    for name in lane_names:
        latest = max(by_lane[name], key=lambda exp: exp.created_at)
        tip_id = branches.get(name)
        lanes.append(
            {
                "experiment_id": name,
                "index": lane_index[name],
                "title": experiments[tip_id].title if tip_id else latest.title,
                "is_active": tip_id is not None,
                "tip_version_id": tip_id,
                "tip_label": f"v{numbers[tip_id]['version']}" if tip_id else None,
            }
        )

    tip_ids = set(branches.values())
    nodes = [
        {
            "version_id": exp.id,
            "experiment_id": line_of(exp),
            "lane": lane_index[exp.branch],
            "version": numbers[exp.id]["version"],
            "label": f"v{numbers[exp.id]['version']}",
            "change_level": numbers[exp.id]["level"],
            "title": exp.title,
            "created_at": exp.created_at.isoformat(),
            "author": exp.author,
            "is_tip": exp.id in tip_ids,
            "is_merge": len(dag[exp.id]) > 1,
            "refs": sorted(ref_names.get(exp.id, [])),
            "structure_kind": _structure_kind(exp.structure_type),
            "has_process": "structureforge_process" in exp.metadata,
        }
        for exp in sorted((experiments[exp_id] for exp_id in keep), key=lambda exp: (exp.created_at, exp.id))
    ]

    edges = []
    collapsed = versioning.collapsed_dag(dag, keep)
    for child in (node["version_id"] for node in nodes):  # dans l'ordre des nœuds
        merge = len(dag[child]) > 1
        for i, parent in enumerate(collapsed[child]):
            same_line = experiments[parent].branch == experiments[child].branch
            if i > 0 or (merge and not same_line):
                kind = "merge"
            else:
                kind = "parent" if same_line else "fork"
            edges.append({"parent": parent, "child": child, "kind": kind})
    return {"lanes": lanes, "nodes": nodes, "edges": edges}


def lineage_graph(repo: Any, *, anchors: Any = (), attachments: Any = ()) -> dict:
    """The ``{"nodes", "edges"}`` payload of the µprojet's lineage (``GET .../lineage``, see
    :func:`spectre.plugins.experiments.api.microproject_lineage` for what each node means) for one
    repository - shared with the frise of a thématique (:mod:`spectre.plugins.experiments.insights`),
    which lays out the same nodes on a time axis, and with the lots (:mod:`spectre.plugins.lots.views`).
    Each node is a version (``version_id``, also its ``id`` in ``edges``) of a line of study
    (``experiment_id``), the line's tip or not (``is_tip``). The lots holding a node's wafers are
    the lots plugin's own (``GET /api/lots?wafer=``) : the page composes their badges.

    ``anchors`` (version ids) adds ``{"anchors": {version_id: node id | None}}`` : the node that
    shows each of these versions (``None`` for one no longer in the repository) - where the
    µprojet page hangs a planned experiment (:mod:`.plans`) that continues it.

    ``attachments`` (:func:`.attachments.graph_attachments` : ``{root, parent, author, created_at}``
    in version ids) adds an edge from the node showing ``parent`` to the node of the floating line
    starting at ``root``, marked ``attached`` (``{author, created_at}``) - drawn as a link set by
    hand, not a filiation. It counts as a continuation like any other edge."""
    experiments = {exp.id: exp for exp in repo}
    if not experiments:
        return {"nodes": [], "edges": [], **({"anchors": dict.fromkeys(anchors)} if anchors else {})}

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
        structural point ``anchor_id``: its first commit after the node it hangs from
        (:func:`hung_from`)."""
        start = experiments[exp_id].created_at
        parents = dag[exp_id]
        while len(parents) == 1 and parents[0] != anchor_id and parents[0] not in tips:
            exp_id = parents[0]
            start = experiments[exp_id].created_at
            parents = dag[exp_id]
        return start

    def hung_from(exp_id: str, anchor_id: str) -> str:
        """The node a tip forked off the structural point ``anchor_id`` hangs from: the nearest
        other tip it descends from on the way back - a study started from another one without
        changing the structure (tests on the same wafers...) stays under it -, else that point."""
        parents = dag[exp_id]
        while len(parents) == 1 and parents[0] != anchor_id:
            if parents[0] in tips:
                return parents[0]
            parents = dag[parents[0]]
        return anchor_id

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
        # la piste du point structurel continue sans changer la structure : son bout le remplace,
        # même quand d'autres pistes en partent aussi (sinon la même étude s'affiche deux fois)
        own_tip = repo.branches.get(experiments[exp_id].branch)
        if not already_a_tip and own_tip in resolved_tips and len(resolved_tips) > 1:
            display_id[exp_id] = own_tip
            nodes.append(node_payload(own_tip, is_tip=True, is_merge_id=exp_id, started_at=started_at))
            for tip_id in resolved_tips:
                if tip_id != own_tip:
                    nodes.append(
                        node_payload(tip_id, is_tip=True, is_merge_id=exp_id, started_at=line_start(tip_id, exp_id))
                    )
        elif not already_a_tip and len(resolved_tips) == 1:
            display_id[exp_id] = resolved_tips[0]
            nodes.append(node_payload(resolved_tips[0], is_tip=True, is_merge_id=exp_id, started_at=started_at))
        else:
            display_id[exp_id] = exp_id
            nodes.append(node_payload(exp_id, is_tip=already_a_tip, is_merge_id=exp_id, started_at=started_at))
            for tip_id in resolved_tips:  # only non-empty when ambiguous (len > 1) - see docstring
                nodes.append(
                    node_payload(tip_id, is_tip=True, is_merge_id=exp_id, started_at=line_start(tip_id, exp_id))
                )

    def shown_as(exp_id: str) -> str:
        """The node that shows ``exp_id``: itself for a tip (always a node), else its structural
        point's (the tip displayed in its place, say)."""
        if exp_id in tips:
            return exp_id
        return display_id[exp_id if exp_id in structural_ids else nearest_structural_ancestor(exp_id)]

    edges = []
    for child, parents in collapsed.items():
        if len(dag[child]) > 1:
            # a combination: an edge from the node of each study it was made of - two tips forked
            # off the same structural point are two nodes, which collapsing would fold into one
            parents = list(dict.fromkeys(shown_as(parent) for parent in dag[child]))
        else:
            parents = [display_id[parent] for parent in parents]
        edges.extend({"parent": parent, "child": display_id[child]} for parent in parents)
    for exp_id, resolved_tips in tips_by_anchor.items():
        if len(resolved_tips) > 1:
            edges.extend(
                {"parent": shown_as(hung_from(tip_id, exp_id)), "child": tip_id}
                for tip_id in resolved_tips
                if tip_id != display_id[exp_id]
            )

    for attachment in attachments:
        parent, child = shown_as(attachment["parent"]), shown_as(attachment["root"])
        if parent != child:
            edges.append({"parent": parent, "child": child, "attached": {"author": attachment["author"], "created_at": attachment["created_at"]}})

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
        # ses places (une par variante, ses réplicats sinon) : combien, combien associées, et si
        # l'étude a déjà ses FDL - la couleur du badge (rouge / orange / vert)
        places = experiments[node["id"]].metadata.get("physical_tracking", [])
        node["plates"] = {
            "total": len(places),
            "named": sum(1 for e in places if e.get("sample_id")),
            "has_fdl": bool(study_fdl(experiments[node["id"]].metadata)),
        }

    if anchors:
        return {"nodes": nodes, "edges": edges, "anchors": {vid: shown_as(vid) if vid in experiments else None for vid in anchors}}
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
