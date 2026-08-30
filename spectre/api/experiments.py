"""Experiment endpoints: wraps ``follow.storage.repository.Repository`` for one project. Deep
logic (versioning, diffing, DOE) stays in ``follow``; turning a re-edited process into a new
committed version goes through ``structureforge.adapters.follow_adapter.derive_experiment`` (added
in this repository's StructureForge branch specifically for Spectre's "evolve" flow). This module
only resolves which project's repository to use and translates errors into HTTP responses.

Route order matters: ``{ref:path}`` is greedy (it matches slashes too - see
``follow/api/app.py``'s own note on the same trick), so every route with a literal suffix after
``{ref:path}`` (``/process``, ``/timeline``, ``/diff``, ``/evoluer``, ``/conclure``) is registered
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
from .structures import LaunchExperienceRequest

router = APIRouter(prefix="/api/projects", tags=["experiments"])

RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}

CAMPAIGN_FIELD_LABELS = {"thickness": "Épaisseur", "depth": "Profondeur", "target_level": "Niveau cible"}


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


def _detail(experiment: Any) -> dict:
    return {
        "id": experiment.id,
        "parents": list(experiment.parents),
        "branch": experiment.branch,
        "created_at": experiment.created_at.isoformat(),
        "author": experiment.author,
        "title": experiment.title,
        "intent": experiment.intent,
        "hypothesis": experiment.hypothesis,
        "status": experiment.conclusion.status,
        "objectives": [o.model_dump(mode="json") for o in experiment.objectives],
        "conclusion": experiment.conclusion.model_dump(mode="json"),
        "references": [r.model_dump(mode="json") for r in experiment.references],
        "tags": list(experiment.tags),
        "structure_svg": structures.render_structure_svg(experiment.structure_type, experiment.structure),
        "is_batch": experiment.structure_type == structures.ProcessLot.registry_key(),
        "has_editable_process": "structureforge_process" in experiment.metadata,
        "evidence": [e.model_dump(mode="json") for e in experiment.evidence],
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
        builder = follow_adapter.derive_experiment(
            repo,
            ref,
            geometry,
            body.steps,
            title=body.title,
            intent=body.intent,
            author=user.name,
            hypothesis=body.hypothesis,
            carry_objectives=not body.objectives,
        )
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc

    if body.objectives:
        builder.objectives = [follow.Objective(**o.model_dump(exclude_none=True)) for o in body.objectives]
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps)

    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    builder = repo.derive(ref, title=parent.title, intent=parent.intent, author=user.name)
    builder.metadata = dict(parent.metadata)
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    builder = repo.derive(ref, title=parent.title, intent=parent.intent, author=user.name)
    builder.metadata = dict(parent.metadata)
    builder.evidence = list(parent.evidence)
    builder.add_evidence(
        id=secrets.token_hex(6),
        description=body.description,
        source=body.source,
        metrics=metric or {},
    )
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": experiment.id}


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

    # The generic diff Follow computes names raw structure paths (e.g. "layers[1].rings[0]..."),
    # which is exactly the internal jargon Spectre's UI avoids everywhere else. Since Spectre is
    # also the only thing that ever creates a ProcessLot (via the guided campaign builder - see
    # :mod:`spectre.api.structures`), it already knows in plain terms what was varied: surface
    # that as `factor_label`/`factor_values` so the page can lead with it and keep the raw path
    # table as a secondary, opt-in detail rather than the headline.
    plan = experiment.metadata.get("campaign_plan")
    process = experiment.metadata.get("structureforge_process")
    if plan and process:
        try:
            step = process["steps"][plan["step_index"]]
            payload["factor_label"] = f"{CAMPAIGN_FIELD_LABELS.get(plan['field'], plan['field'])} — {step['name']}"
            payload["factor_values"] = plan["values"]
        except (KeyError, IndexError, TypeError):
            pass
    return payload


@router.get("/{slug}/experiences/{ref:path}")
def get_experience(ref: str, project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    return _detail(experiment)
