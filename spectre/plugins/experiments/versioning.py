"""A process/structure version number (X.Y.Z), computed on top of Follow's generic commit chain
- not a new storage concept, purely derived from ``Experiment.metadata["structureforge_process"]``
(see :mod:`spectre.plugins.structures.simulation`) at read time. This is deliberately Spectre-side, not
``follow``'s: Follow's own versioning (a commit per mutation, `evolution légère`) already treats
every field the same way on purpose, since it has no notion of what "structural" even means for
an arbitrary domain. What counts as a major/minor/patch change here is specific to a StructureForge
process (a substrate + an ordered list of ``structureforge.process.steps.ProcessStep``), so it
lives here instead.

Rules, from the coarsest to the finest-grained:

- **major (X)** - the substrate changed, or the step list's *shape* changed (a step was added,
  removed, or reordered - detected as the sequence of step ``kind``s no longer matching).
- **minor (Y)** - the step list has the same shape, but at least one field other than a step's
  ``name`` differs (a material, a recipe, a thickness, an orientation...) - anything that can
  actually change the simulated geometry.
- **patch (Z)** - the only difference is a step's ``name`` - a label with zero effect on the
  simulation (see ``structureforge.process.simulate._apply``, which never reads ``name``) -, the
  unit of a declared parameter written down or removed (not replaced by another one: that changes
  the value, a minor change), or the layer labels drawn beside the structure
  (``process_layer_labels``, see :class:`spectre.plugins.structures.simulation.LayerLabel`) and
  their grouping by brick (``process_bricks``, only as far as it groups labels), which never touch
  the process. The bricks of a process alone change nothing: a version that only regroups
  unlabelled steps is ``none``.
- **none** - the process is byte-identical; whatever changed on this commit (a tag, a title, a
  piece of evidence...) isn't a process/structure change at all.

A structure given as a picture (:class:`spectre.plugins.structures.kinds.StructureImage`) has no process
to compare - its "signature" is the token stored under ``structure_image_revision``, renewed on
each real launch/evolution and kept by everything else (replacing the picture included): a new
token, or a switch between a drawn and a pictured structure, is a **major** change, since nothing
tells how big it was; the same token is **none**.

Everything that isn't a process/structure change still gets its own immutable Follow commit -
that full chain is the "historique complet" a fiche shows in full; this module only picks out,
and numbers, the subset of it that actually moved the process/structure forward.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal

from ..structures.simulation import (
    BRICKS_METADATA_KEY,
    LAYER_LABELS_METADATA_KEY,
    MIN_GROUPED_LABELS,
    split_declared_unit,
)

ChangeLevel = Literal["initial", "major", "minor", "patch", "none"]

VERSION_CHANGE_LEVELS: tuple[ChangeLevel, ...] = ("initial", "major", "minor", "patch", "none")


def _step_shape(steps: list[dict]) -> list[str]:
    return [step.get("kind") for step in steps]


def _step_without_name(step: dict) -> dict:
    return {k: v for k, v in step.items() if k != "name"}


def _label_groups(metadata: dict[str, Any], labels: dict[str, Any]) -> list[dict[str, Any]]:
    """Ce que les briques du procédé (``process_bricks``) changent au dessin des étiquettes : les
    briques dont les étiquettes n'en font qu'une (au moins ``MIN_GROUPED_LABELS`` étapes
    étiquetées), leur nom et ces étapes. Le reste de l'appartenance aux briques ne se voit pas."""
    groups = []
    bricks = metadata.get(BRICKS_METADATA_KEY)
    for brick in bricks if isinstance(bricks, list) else []:
        if not isinstance(brick, dict):
            continue
        members = [step_id for step_id in brick.get("step_ids") or [] if step_id in labels]
        if len(members) >= MIN_GROUPED_LABELS:
            groups.append({"name": brick.get("name"), "step_ids": members})
    return groups


def structure_signature(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """What versioning compares for one commit: its StructureForge process (with its layer labels
    under ``"layer_labels"``, when it has some - a version without any compares as before them -
    and, under ``"label_groups"``, the bricks whose labelled steps share one label), or - for a
    structure given as a picture - its revision token (see the module docstring). ``None`` when
    there is neither. The bricks of the process count only through the labels they group: alone,
    they never change the version."""
    process = metadata.get("structureforge_process")
    if process is not None:
        labels = metadata.get(LAYER_LABELS_METADATA_KEY)
        if not labels:
            return process
        if isinstance(labels, dict):
            # la place d'une étiquette déplacée à la main (offset) ne change pas la version
            labels = {sid: {k: v for k, v in label.items() if k != "offset"} if isinstance(label, dict) else label for sid, label in labels.items()}
        groups = _label_groups(metadata, labels) if isinstance(labels, dict) else []
        return {**process, "layer_labels": labels, **({"label_groups": groups} if groups else {})}
    revision = metadata.get("structure_image_revision")
    if revision is not None:
        return {"image_revision": revision}
    return None


def classify_process_change(before: dict[str, Any] | None, after: dict[str, Any]) -> ChangeLevel:
    """Classify the process/structure change from ``before`` to ``after`` (both the
    ``{"substrate": ..., "steps": [...]}`` shape :func:`spectre.plugins.structures.simulation.process_metadata`
    produces). ``before=None`` means there is nothing to compare against (a lineage's very first
    commit) - reported as ``"initial"``, never ``"major"``, so a caller can tell "this is where
    the process started" apart from "something structural changed".
    """
    if before is None:
        return "initial"
    if before == after:
        return "none"

    # une structure en image (ou le passage dessin <-> image) : aucune idée de l'ampleur du changement
    if "image_revision" in before or "image_revision" in after:
        return "major"

    if before.get("substrate") != after.get("substrate"):
        return "major"

    before_steps: list[dict] = before.get("steps", [])
    after_steps: list[dict] = after.get("steps", [])
    if _step_shape(before_steps) != _step_shape(after_steps):
        return "major"

    if any(_step_without_name(b) != _step_without_name(a) for b, a in zip(before_steps, after_steps)):
        return "minor"

    # un paramètre déclaré (dopage, précurseur... - voir structures.process_metadata) est un réglage
    # de l'étape comme un autre, pas un simple renommage ; son unité ajoutée (ou retirée) seule ne
    # fait que l'écrire, mais une unité remplacée par une autre change sa valeur
    if _declared_change(before.get("declared_params", {}), after.get("declared_params", {})) == "minor":
        return "minor"

    # a step renamed, a unit written down, or only the layer labels changed: nothing the simulation reads
    return "patch"


def _declared_change(before: Any, after: Any) -> Literal["none", "patch", "minor"]:
    """Ce que change le passage des paramètres déclarés ``before`` à ``after`` (par position
    d'étape) : ``minor`` pour un réglage (un paramètre, une valeur, une obtention, une unité
    remplacée par une autre), ``patch`` quand seule une unité est ajoutée ou retirée - ou passe de
    l'obtention au champ ``unit`` -, ``none`` sinon."""
    if before == after:
        return "none"
    if not isinstance(before, dict) or not isinstance(after, dict) or set(before) != set(after):
        return "minor"
    for key in before:
        old, new = before[key], after[key]
        if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
            return "minor"
        for old_param, new_param in zip(old, new):
            old_rest, old_unit = split_declared_unit(old_param)
            new_rest, new_unit = split_declared_unit(new_param)
            if old_rest != new_rest or (old_unit and new_unit and old_unit != new_unit):
                return "minor"
    return "patch"


def same_settings(before: dict[str, Any] | None, after: dict[str, Any]) -> bool:
    """Si le procédé ``after`` règle les étapes exactement comme ``before`` (deux
    ``structureforge_process``) : le même, ou le même à une unité de paramètre déclaré près, ajoutée
    ou retirée - une évolution qui ne fait que cela garde la conclusion, comme pour les
    étiquettes."""
    if not isinstance(before, dict) or before == after:
        return before == after
    rest_before = {key: value for key, value in before.items() if key != "declared_params"}
    rest_after = {key: value for key, value in after.items() if key != "declared_params"}
    return rest_before == rest_after and _declared_change(before.get("declared_params", {}), after.get("declared_params", {})) != "minor"


def changes_structure(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Whether a commit whose metadata is ``after``, derived from one whose metadata is ``before``,
    moved the process/structure forward (any level but ``"none"``)."""
    after_signature = structure_signature(after)
    return after_signature is not None and classify_process_change(structure_signature(before), after_signature) != "none"


def structural_versions(history: list[Any]) -> list[Any]:
    """The entries of ``history`` (oldest first, a first-parent lineage) that moved the
    process/structure forward - the frise's structure versions, its first one included."""
    levels = compute_branch_versions(history)
    return [exp for exp in history if levels[exp.id]["level"] != "none"]


def _bump(version: tuple[int, int, int], level: ChangeLevel) -> tuple[int, int, int]:
    x, y, z = version
    if level in ("initial", "major"):
        return (x + 1, 0, 0) if level == "major" else (1, 0, 0)
    if level == "minor":
        return (x, y + 1, 0)
    if level == "patch":
        return (x, y, z + 1)
    return version  # "none"


def compute_branch_versions(history: list[Any]) -> dict[str, dict[str, Any]]:
    """Assign a version to every experiment in ``history`` (oldest first - e.g.
    ``reversed(repo.log(ref))``), one linear lineage at a time. Returns
    ``{experiment_id: {"version": "X.Y.Z", "level": ChangeLevel}}`` for *every* entry, including
    the ones that didn't bump anything (``level="none"``) - those simply keep the version their
    predecessor already had, which is exactly what lets a caller show "this evidence was added
    while at v1.2.0" in the full history without it being its own version.
    """
    out: dict[str, dict[str, Any]] = {}
    version = (0, 0, 0)
    previous_process: dict[str, Any] | None = None
    for exp in history:
        process = structure_signature(exp.metadata)
        level = classify_process_change(previous_process, process) if process is not None else "none"
        version = _bump(version, level)
        out[exp.id] = {"version": "{}.{}.{}".format(*version), "level": level}
        if process is not None:
            previous_process = process
    return out


def _topological_order(dag: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm, iterative - mirrors ``follow.presentation.graphing._depths``'s own
    reasoning for avoiding recursion here: a recursive walk's stack depth would depend on the
    lineage's length and the dict's iteration order, which is not guaranteed.
    """
    parents = {node: [p for p in dag.get(node, []) if p in dag] for node in dag}
    children: dict[str, list[str]] = {node: [] for node in dag}
    for node, node_parents in parents.items():
        for parent in node_parents:
            children[parent].append(node)

    remaining = {node: len(node_parents) for node, node_parents in parents.items()}
    queue = deque(sorted(node for node, count in remaining.items() if count == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in children[node]:
            remaining[child] -= 1
            if remaining[child] == 0:
                queue.append(child)
    return order


def determine_keep_ids(dag: dict[str, list[str]], processes: dict[str, dict | None], tips: set[str]) -> set[str]:
    """Which experiments stay visible in a collapsed microproject graph: every root, every merge (a
    join between two lines of work is structurally significant on its own, whatever it did or
    didn't change), every branch tip (so "where things stand" is never hidden), and every commit
    that actually bumped the process/structure version. Everything else - a tag, an evidence, a
    title edit riding on an otherwise-unchanged process - gets collapsed out.

    ``processes`` maps experiment id to its :func:`structure_signature` (or ``None``).
    """
    keep: set[str] = set()
    for node, parents in dag.items():
        if len(parents) != 1 or node in tips:
            keep.add(node)
            continue
        level = classify_process_change(processes.get(parents[0]), processes.get(node))
        if level != "none":
            keep.add(node)
    return keep


def collapsed_dag(dag: dict[str, list[str]], keep: set[str]) -> dict[str, list[str]]:
    """``dag`` with every id not in ``keep`` removed, and edges reconnected straight through them
    so a kept node's parents in the result are its nearest *kept* ancestors - the same relationship
    the original graph described, just without the commits nobody needs to see on it.
    """
    order = _topological_order(dag)
    nearest_kept: dict[str, list[str]] = {}
    for node in order:
        if node in keep:
            nearest_kept[node] = [node]
            continue
        acc: list[str] = []
        seen: set[str] = set()
        for parent in dag.get(node, []):
            for ancestor in nearest_kept.get(parent, []):
                if ancestor not in seen:
                    seen.add(ancestor)
                    acc.append(ancestor)
        nearest_kept[node] = acc

    new_dag: dict[str, list[str]] = {}
    for node in dag:
        if node not in keep:
            continue
        acc = []
        seen = set()
        for parent in dag[node]:
            for ancestor in nearest_kept.get(parent, []):
                if ancestor not in seen:
                    seen.add(ancestor)
                    acc.append(ancestor)
        new_dag[node] = acc
    return new_dag
