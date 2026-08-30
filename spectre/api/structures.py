"""Structure definition and launch: materials/recipes pickers, the simulation preview, and
turning a simulated process into a new tracked experience. All simulation and rendering logic is
``structureforge``'s (see :mod:`spectre.core.structures`); Follow's part (committing the result) is
``structureforge.adapters.follow_adapter``, extended in this repository with ``build_experiment``
for exactly this "commit once fully formed" use.
"""

from __future__ import annotations

import re

import follow
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from structureforge.adapters import follow_adapter
from structureforge.core.recipes import DepositionRecipe, EtchRecipe
from structureforge.process.steps import ProcessStep

from ..core import projects, structures
from ..core.accounts import User
from ..core.permissions import require_role
from ..core.projects import Project
from .deps import get_current_user

router = APIRouter(prefix="/api/projects", tags=["structures"])


class NewStructureRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]


class ObjectiveInput(BaseModel):
    name: str
    metric: str
    direction: str = "observe"
    target: float | None = None
    tolerance: float | None = None
    rationale: str | None = None  # pourquoi cet objectif compte
    verification_method: str | None = None  # comment on prévoit de le vérifier


class LaunchExperienceRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    title: str
    intent: str
    hypothesis: str | None = None
    objectives: list[ObjectiveInput] = []
    new_branch: str | None = None  # only meaningful when evolving: fork instead of continuing


class CampaignPreviewRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    plan: structures.VariantPlan


class LaunchCampaignRequest(CampaignPreviewRequest):
    title: str
    intent: str
    hypothesis: str | None = None
    objectives: list[ObjectiveInput] = []


def _slugify_branch(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "experience"


def _unique_branch(repo: "follow.Repository", title: str) -> str:
    base = _slugify_branch(title)
    branch = base
    suffix = 2
    while branch in repo.branches:
        branch = f"{base}-{suffix}"
        suffix += 1
    return branch


def split_objectives(inputs: list[ObjectiveInput]) -> tuple[list["follow.Objective"], dict[str, str]]:
    """``follow.Objective`` has no "how will we check this" field (only ``rationale``, the *why*)
    - ``verification_method`` is Spectre-specific, so it's kept out of the ``Objective`` itself and
    returned separately, to be stashed under ``Experiment.metadata["objective_verification"]``
    (keyed by objective name) the same way ``structureforge_process`` already rides along there.
    """
    objectives: list[follow.Objective] = []
    verification: dict[str, str] = {}
    for o in inputs:
        data = o.model_dump(exclude_none=True, exclude={"verification_method"})
        objectives.append(follow.Objective(**data))
        if o.verification_method:
            verification[o.name] = o.verification_method
    return objectives, verification


@router.get("/{slug}/materials")
def list_materials(project: Project = Depends(require_role("viewer"))) -> list[dict]:
    return [m.model_dump(mode="json") for m in structures.materials_library()]


@router.get("/{slug}/recipes")
def list_recipes(project: Project = Depends(require_role("viewer"))) -> dict:
    custom = projects.get_recipe_store(project.slug).load()
    combined = structures.recipes_library(project.slug)
    return {
        "deposition": [
            {**r.model_dump(mode="json"), "is_custom": r.name in custom.deposition} for r in combined.deposition.values()
        ],
        "etch": [{**r.model_dump(mode="json"), "is_custom": r.name in custom.etch} for r in combined.etch.values()],
    }


@router.post("/{slug}/recipes/deposition")
def upsert_deposition_recipe(recipe: DepositionRecipe, project: Project = Depends(require_role("editor"))) -> dict:
    projects.get_recipe_store(project.slug).upsert_deposition(recipe)
    return list_recipes(project)


@router.delete("/{slug}/recipes/deposition/{name}")
def delete_deposition_recipe(name: str, project: Project = Depends(require_role("editor"))) -> dict:
    projects.get_recipe_store(project.slug).remove_deposition(name)
    return list_recipes(project)


@router.post("/{slug}/recipes/etch")
def upsert_etch_recipe(recipe: EtchRecipe, project: Project = Depends(require_role("editor"))) -> dict:
    projects.get_recipe_store(project.slug).upsert_etch(recipe)
    return list_recipes(project)


@router.delete("/{slug}/recipes/etch/{name}")
def delete_etch_recipe(name: str, project: Project = Depends(require_role("editor"))) -> dict:
    projects.get_recipe_store(project.slug).remove_etch(name)
    return list_recipes(project)


@router.post("/{slug}/structures/simulate")
def simulate_structure(body: NewStructureRequest, project: Project = Depends(require_role("editor"))) -> dict:
    try:
        _geometry, frames, materials = structures.run_simulation(project.slug, body.substrate, body.steps)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return structures.frames_payload(frames, materials)


@router.post("/{slug}/experiences", status_code=201)
def launch_experience(
    body: LaunchExperienceRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        geometry, _frames, _materials = structures.run_simulation(project.slug, body.substrate, body.steps)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = projects.get_repository(project.slug)
    branch = _unique_branch(repo, body.title)
    objectives, verification = split_objectives(body.objectives)

    builder = follow_adapter.build_experiment(
        repo,
        geometry,
        body.steps,
        branch=branch,
        title=body.title,
        intent=body.intent,
        author=user.name,
        hypothesis=body.hypothesis,
        objectives=objectives,
    )
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps)
    if verification:
        builder.metadata["objective_verification"] = verification
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/structures/variantes")
def preview_campaign(body: CampaignPreviewRequest, project: Project = Depends(require_role("editor"))) -> dict:
    """A preview of a DOE campaign: one simulated variant per combination of ``body.plan.factors``
    (fully crossed), plus the constant/varying split (``follow.doe.batch.analyze_batch``) - the
    "matrice de split", available before anyone commits to the campaign.
    """
    try:
        result = structures.generate_campaign_variants(project.slug, body.substrate, body.steps, body.plan)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "svgs": result.svgs,
        "variation": result.variation.model_dump(mode="json"),
        "labels": result.labels,
        "factor_labels": result.factor_labels,
        "factor_values": result.factor_values,
    }


@router.post("/{slug}/experiences/campagne", status_code=201)
def launch_campaign(
    body: LaunchCampaignRequest,
    project: Project = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Commit a whole DOE campaign as one experience: a ``ProcessLot`` holding one flattened
    variant per combination of ``body.plan.factors`` (fully crossed), with ``body.steps`` (the
    reference process) as the shared protocol - the same "one experiment, many entities" shape
    ``follow.doe.batch``/``follow/api/app.py`` already use generically for any domain.
    """
    try:
        result = structures.generate_campaign_variants(project.slug, body.substrate, body.steps, body.plan)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = projects.get_repository(project.slug)
    branch = _unique_branch(repo, body.title)
    objectives, verification = split_objectives(body.objectives)
    lot = structures.ProcessLot(entries=result.entries)

    builder = repo.new(
        branch=branch,
        structure=lot,
        title=body.title,
        intent=body.intent,
        author=user.name,
        hypothesis=body.hypothesis,
        objectives=objectives,
        steps=follow_adapter.to_steps(body.steps),
    )
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps)
    builder.metadata["campaign_labels"] = result.labels
    builder.metadata["campaign_factor_labels"] = result.factor_labels
    builder.metadata["campaign_factor_values"] = result.factor_values
    if verification:
        builder.metadata["objective_verification"] = verification
    try:
        experiment = builder.commit()
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"id": experiment.id, "branch": experiment.branch}
