"""Experiment endpoints: wraps ``follow.storage.repository.Repository`` for one project. Deep
logic (versioning, diffing, DOE) stays in ``follow``; turning a re-edited process into a new
committed version goes through ``structureforge.adapters.follow_adapter.derive_experiment`` (added
in this repository's StructureForge branch specifically for Spectre's "evolve" flow). This module
only resolves which project's repository to use and translates errors into HTTP responses.

Route order matters: ``{ref:path}`` is greedy (it matches slashes too - see
``follow/api/app.py``'s own note on the same trick), so every route with a literal suffix after
``{ref:path}`` (``/process``, ``/timeline``, ``/diff``, ``/evoluer``, ``/conclure``, ``/preuves``,
``/combiner``, ``/etiquettes``, ``/entites``, ``/diff-externe``, ``/matrice``) is registered
before the bare "get one experience" route below it - otherwise that catch-all would swallow them.
"""

from __future__ import annotations

import secrets
from typing import Any

import follow
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from structureforge.adapters import follow_adapter

from ..core import projects, structures
from ..core.accounts import User
from ..core.permissions import get_project as resolve_project
from ..core.permissions import require_role
from ..core.projects import Project
from .deps import get_current_user
from .structures import LaunchExperienceRequest, _unique_branch, split_objectives

router = APIRouter(prefix="/api/projects", tags=["experiments"])

RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}


def _derive_branch(repo: "follow.Repository", parent: Any, requested: str | None) -> str | None:
    """Which branch to derive onto. An explicit fork request wins; otherwise continue the
    parent's own branch as long as it's still the tip. If someone else already evolved past this
    exact version (its branch has moved on), silently continue on a fresh branch instead of
    letting Follow's own branch-collision error - raw, in English, full of git vocabulary -
    reach a non-technical user.
    """
    if requested:
        return requested
    if repo.branches.get(parent.branch) == parent.id:
        return None
    return _unique_branch(repo, parent.title)


class ObjectiveResultInput(BaseModel):
    objective: str
    status: str
    observed: dict[str, Any] | None = None
    reasoning: str | None = None


class ConcludeRequest(BaseModel):
    status: str = "concluded"
    decision: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    objective_results: list[ObjectiveResultInput] = []


class EvidenceInput(BaseModel):
    description: str
    source: str
    metric_name: str | None = None
    metric_value: float | None = None
    metric_unit: str | None = None


class CombineRequest(BaseModel):
    other_id: str
    title: str
    intent: str


class TagsRequest(BaseModel):
    tags: list[str]


class EntityTrackingInput(BaseModel):
    sample_id: str | None = None
    location: str | None = None


class PhysicalTrackingRequest(BaseModel):
    entities: list[EntityTrackingInput]


def _not_found(exc: follow.ExperimentNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc.args[0]) if exc.args else "expérience introuvable")


def _summary(experiment: Any) -> dict:
    return {
        "id": experiment.id,
        "title": experiment.title,
        "intent": experiment.intent,
        "status": experiment.conclusion.status,
        "author": experiment.author,
        "created_at": experiment.created_at.isoformat(),
        "branch": experiment.branch,
        "tags": list(experiment.tags),
    }


def _detail(experiment: Any, repo: Any = None) -> dict:
    # Every experiment whose own parents include this one - i.e. a version derived from here.
    # More than one means this version is a fork point: two (or more) lines of work continued
    # from it independently. repo is optional (a caller without one, if any, just skips this).
    children = (
        [{"id": exp.id, "title": exp.title, "branch": exp.branch} for exp in repo if experiment.id in exp.parents]
        if repo is not None
        else []
    )
    return {
        "id": experiment.id,
        "parents": list(experiment.parents),
        "branch": experiment.branch,
        "children": children,
        "created_at": experiment.created_at.isoformat(),
        "author": experiment.author,
        "title": experiment.title,
        "intent": experiment.intent,
        "hypothesis": experiment.hypothesis,
        "status": experiment.conclusion.status,
        "objectives": [o.model_dump(mode="json") for o in experiment.objectives],
        "objective_verification": experiment.metadata.get("objective_verification", {}),
        "conclusion": experiment.conclusion.model_dump(mode="json"),
        "references": [r.model_dump(mode="json") for r in experiment.references],
        "tags": list(experiment.tags),
        "structure_svg": structures.render_structure_svg(experiment.structure_type, experiment.structure),
        "is_batch": experiment.structure_type == structures.ProcessLot.registry_key(),
        "has_editable_process": "structureforge_process" in experiment.metadata,
        "evidence": [e.model_dump(mode="json") for e in experiment.evidence],
        "physical_tracking": experiment.metadata.get("physical_tracking", []),
    }


@router.get("/{slug}/experiences")
def list_experiences(
    status: str = "all", offset: int = 0, limit: int = 30, project: Project = Depends(require_role("viewer"))
) -> dict:
    """Newest first, paginated - mirrors the ``{items, total, offset, limit}`` shape
    ``follow/api/app.py``'s own ``/api/experiments`` already uses, since a project's history is
    exactly the kind of list that can outgrow "load everything at once" as it grows.
    """
    if status not in ("all", "running", "concluded"):
        raise HTTPException(status_code=422, detail="status doit être 'all', 'running' ou 'concluded'")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset doit être >= 0")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit doit être entre 1 et 200")
    wanted = RUNNING_STATUSES if status == "running" else CONCLUDED_STATUSES if status == "concluded" else None

    repo = projects.get_repository(project.slug)
    matches = [exp for exp in repo if wanted is None or exp.conclusion.status in wanted]
    matches.sort(key=lambda exp: exp.created_at, reverse=True)
    page = matches[offset : offset + limit]
    return {"items": [_summary(exp) for exp in page], "total": len(matches), "offset": offset, "limit": limit}


@router.get("/{slug}/graphe.html", response_class=HTMLResponse)
def project_graph_html(project: Project = Depends(require_role("viewer"))) -> str:
    """The project's full lineage as a self-contained Plotly page - the same figure Follow's own
    GUI embeds (``follow.presentation.graphing.build_graph_figure``), served directly so the
    "vue d'ensemble" page can drop it into an iframe. An advanced, opt-in view: the fiche's own
    frise chronologique (see :mod:`spectre.api.static.js.experience`) is the everyday one.
    """
    repo = projects.get_repository(project.slug)
    if len(repo) == 0:
        return (
            "<p style='font-family: \"IBM Plex Sans\", sans-serif; padding: 1.5rem; color:#5c655e;'>"
            "Aucune expérience à afficher pour l'instant.</p>"
        )
    from follow.presentation.graphing import build_graph_figure

    figure = build_graph_figure(repo)
    figure.update_layout(title="Vue d'ensemble du projet")
    # Follow's own figure labels branch tips and hover text with raw git vocabulary ("branche:
    # ...", bare branch slugs) - not fit for Spectre's non-technical audience, so scrub it here
    # rather than in Follow, which is deliberately generic.
    if len(figure.data) >= 3:
        figure.data = figure.data[:2]
    node_trace = figure.data[1]
    scrubbed_hover = [
        "<br>".join(line for line in text.split("<br>") if not line.startswith("id: ") and not line.startswith("branche: "))
        for text in (node_trace.hovertext or [])
    ]
    node_trace.hovertext = scrubbed_hover
    return figure.to_html(include_plotlyjs=True, full_html=True)


@router.get("/{slug}/experiences/{ref:path}/process")
def experience_process(ref: str, project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    process = experiment.metadata.get("structureforge_process")
    if process is None:
        raise HTTPException(status_code=404, detail="cette expérience n'a pas de procédé éditable enregistré")
    return process


@router.get("/{slug}/experiences/{ref:path}/timeline")
def experience_timeline(ref: str, project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        history = repo.log(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    chronological = list(reversed(history))
    items = [
        {
            "id": exp.id,
            "title": exp.title,
            "intent": exp.intent,
            "created_at": exp.created_at.isoformat(),
            "author": exp.author,
            "is_current": i == len(chronological) - 1,
        }
        for i, exp in enumerate(chronological)
    ]
    return {"items": items}


@router.get("/{slug}/experiences/{ref:path}/diff")
def experience_diff(ref: str, against: str | None = None, project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    target = against
    if target is None:
        baseline = next((r for r in experiment.references if r.role == "baseline" and r.experiment_id), None)
        if baseline is not None:
            target = baseline.experiment_id
        elif experiment.parents:
            target = experiment.parents[0]
    if target is None:
        return {"target": None, "entries": []}

    try:
        diff = repo.diff(target, experiment.id)
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"target": target, **diff.model_dump(mode="json")}


@router.post("/{slug}/experiences/{ref:path}/evoluer", status_code=201)
def evolve_experience(
    ref: str,
    body: LaunchExperienceRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        geometry, _frames, _materials = structures.run_simulation(project.slug, body.substrate, body.steps)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = projects.get_repository(project.slug)
    try:
        parent = repo.get(ref)
        builder = follow_adapter.derive_experiment(
            repo,
            ref,
            geometry,
            body.steps,
            title=body.title,
            intent=body.intent,
            new_branch=_derive_branch(repo, parent, body.new_branch),
            author=user.name,
            hypothesis=body.hypothesis,
            carry_objectives=not body.objectives,
        )
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    builder.metadata = dict(parent.metadata)
    if body.objectives:
        objectives, verification = split_objectives(body.objectives)
        builder.objectives = objectives
        if verification:
            builder.metadata["objective_verification"] = verification
        else:
            builder.metadata.pop("objective_verification", None)
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps)

    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette évolution - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/experiences/{ref:path}/conclure", status_code=201)
def conclude_experience(
    ref: str,
    body: ConcludeRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    objective_results = [
        follow.ObjectiveResult(
            objective=r.objective,
            status=r.status,
            observed=follow.Quantity(**r.observed) if r.observed else None,
            reasoning=r.reasoning,
        )
        for r in body.objective_results
    ]

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=_derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.tags = list(parent.tags)
    builder.conclude(
        status=body.status,
        decision=body.decision,
        summary=body.summary,
        next_steps=body.next_steps,
        objective_results=objective_results,
    )
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette conclusion - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref:path}/preuves", status_code=201)
def add_evidence(
    ref: str,
    body: EvidenceInput,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Attach a piece of evidence (a link, a measurement) to an experience - like ``conclure``,
    this is a lightweight evolution (structure/steps/objectives all carried over unchanged, only
    the evidence list grows) rather than a mutation, since committed experiences are immutable.
    """
    repo = projects.get_repository(project.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    metric = None
    if body.metric_name:
        if body.metric_value is None:
            raise HTTPException(status_code=422, detail="une valeur est requise pour la mesure nommée")
        metric = {body.metric_name: follow.Quantity(value=body.metric_value, unit=body.metric_unit)}

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=_derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    builder.conclusion = parent.conclusion
    builder.add_evidence(
        id=secrets.token_hex(6),
        description=body.description,
        source=body.source,
        metrics=metric or {},
    )
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette preuve - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref:path}/combiner", status_code=201)
def combine_experiences(
    ref: str,
    body: CombineRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Combine two lines of work into one experience - Follow's ``repo.merge()`` supports
    field-by-field conflict resolution (``take_structure``/``take_steps``), which is exactly the
    kind of technical detail Spectre's UI avoids, so this always keeps ``ref``'s structure and
    steps as-is and simply links the other experience in as a second parent, its history and
    evidence still reachable from there. Both sides must be the same kind of structure (a single
    experience can't combine with a campaign).
    """
    repo = projects.get_repository(project.slug)
    try:
        a = repo.get(ref)
        b = repo.get(body.other_id)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    if a.id == b.id:
        raise HTTPException(status_code=422, detail="Choisissez deux expériences différentes.")
    if a.structure_type != b.structure_type:
        raise HTTPException(
            status_code=422,
            detail="Ces deux expériences ne peuvent pas être combinées (par exemple une expérience simple et une campagne).",
        )

    try:
        builder = repo.merge(
            ref,
            body.other_id,
            title=body.title,
            intent=body.intent,
            branch=_derive_branch(repo, a, None),
            author=user.name,
        )
    except follow.FollowError as exc:
        raise HTTPException(status_code=422, detail="Ces deux expériences ne peuvent pas être combinées.") from exc
    builder.metadata = dict(a.metadata)
    builder.tags = list(a.tags)
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible de combiner ces expériences - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref:path}/etiquettes", status_code=201)
def set_tags(
    ref: str,
    body: TagsRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Replace this experience's tag set. Like ``conclure``/``preuves``, this is a lightweight
    evolution - since committed experiences are immutable, "editing" the tags means recording a
    new version that carries the status, structure, and everything else unchanged.
    """
    repo = projects.get_repository(project.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    cleaned: list[str] = []
    for tag in body.tags:
        tag = tag.strip()
        if tag and tag not in cleaned:
            cleaned.append(tag)

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=_derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = cleaned
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer les étiquettes - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "tags": cleaned}


@router.post("/{slug}/experiences/{ref:path}/entites", status_code=201)
def set_physical_tracking(
    ref: str,
    body: PhysicalTrackingRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Attach a physical identifier and storage location to each entity this experience tracks -
    a single sample for an ordinary experience, one per variant for a campaign
    (:class:`spectre.core.structures.ProcessLot`). Purely descriptive bookkeeping Follow has no
    field for, so like tags this rides in ``Experiment.metadata`` and, like ``etiquettes``, is a
    lightweight evolution: recording a new version that carries everything else unchanged.
    """
    repo = projects.get_repository(project.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    expected_count = (
        len(structures.ProcessLot.model_validate(parent.structure).entries)
        if parent.structure_type == structures.ProcessLot.registry_key()
        else 1
    )
    if len(body.entities) != expected_count:
        raise HTTPException(
            status_code=422,
            detail=f"il faut exactement {expected_count} entrée(s) (une par échantillon suivi par cette expérience)",
        )

    def _clean(value: str | None) -> str | None:
        return value.strip() or None if value else None

    entities = [{"sample_id": _clean(e.sample_id), "location": _clean(e.location)} for e in body.entities]

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=_derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = list(parent.tags)
    builder.metadata["physical_tracking"] = entities
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer le suivi physique - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "entities": entities}


@router.get("/{slug}/experiences/{ref:path}/diff-externe")
def experience_diff_external(
    ref: str,
    autre_projet: str,
    autre_experience: str,
    project: Project = Depends(require_role("viewer")),
    user: User = Depends(get_current_user),
) -> dict:
    """Compare this experience's structure against one in a *different* project - Follow's own
    ``repo.diff`` only ever compares within one repository, so this calls
    ``follow.diff_structures`` directly on the two experiments' raw structure dicts instead.
    Requires at least read access to both projects - comparing against a project the caller can't
    see would leak its content through the diff.
    """
    other_project = resolve_project(autre_projet)
    role = projects.role_for(other_project.id, user.id)
    if role is None:
        raise HTTPException(status_code=403, detail="vous n'avez pas accès à cet autre projet")

    repo = projects.get_repository(project.slug)
    other_repo = projects.get_repository(other_project.slug)
    try:
        experiment = repo.get(ref)
        other_experiment = other_repo.get(autre_experience)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    diff = follow.diff_structures(experiment.structure, other_experiment.structure)
    return {
        "target": other_experiment.id,
        "target_project": other_project.name,
        "target_title": other_experiment.title,
        **diff.model_dump(mode="json"),
    }


@router.get("/{slug}/experiences/{ref:path}/matrice")
def experience_batch(ref: str, project: Project = Depends(require_role("viewer"))) -> dict:
    """The constant/varying split of a DOE campaign's variants (``follow.doe.batch.analyze_batch``,
    the same analysis Follow's own GUI calls "matrice de split") - only meaningful for an
    experience whose structure is a :class:`spectre.core.structures.ProcessLot`.
    """
    repo = projects.get_repository(project.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    if experiment.structure_type != structures.ProcessLot.registry_key():
        raise HTTPException(status_code=400, detail="cette expérience n'est pas une campagne à plusieurs variantes")
    lot = structures.ProcessLot.model_validate(experiment.structure)
    variation = follow.analyze_batch(lot.entries)
    payload = variation.model_dump(mode="json")

    # The atlas: one drawn cross-section per entity - StructureForge does the actual rendering
    # (structures.render_lot_svgs), Spectre only lines them up.
    payload["svgs"] = structures.render_lot_svgs(lot)

    # The generic diff Follow computes names raw structure paths (e.g. "layers[1].rings[0]..."),
    # which is exactly the internal jargon Spectre's UI avoids everywhere else. Since Spectre is
    # also the only thing that ever creates a ProcessLot (via the guided campaign builder - see
    # :mod:`spectre.api.structures`), it already computed, in plain terms, what was varied at
    # launch time (`generate_campaign_variants`) and stashed it on the commit - surface that
    # (`factor_labels`/`factor_values`/`labels`) so the page can lead with it and keep the raw
    # path table as a secondary, opt-in detail rather than the headline.
    payload["factor_labels"] = experiment.metadata.get("campaign_factor_labels", [])
    payload["factor_values"] = experiment.metadata.get("campaign_factor_values", [])
    payload["labels"] = experiment.metadata.get("campaign_labels") or [f"#{i + 1}" for i in range(variation.entity_count)]
    payload["physical_tracking"] = experiment.metadata.get("physical_tracking", [])
    return payload


@router.get("/{slug}/experiences/{ref:path}")
def get_experience(ref: str, project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    return _detail(experiment, repo)
