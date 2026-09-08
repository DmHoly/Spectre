"""Structure definition and launch: the materials picker, the simulation preview, and turning a
simulated process into a new tracked experience. All simulation and rendering logic is
``structureforge``'s (see :mod:`spectre.core.structures`); Follow's part (committing the result) is
``structureforge.adapters.follow_adapter``, extended in this repository with ``build_experiment``
for exactly this "commit once fully formed" use.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import follow
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from structureforge.adapters import follow_adapter
from structureforge.process.steps import ProcessStep

from ..core import projects, refs, structures
from ..core.accounts import User
from ..core.permissions import require_role
from ..core.projects import Project
from ..core.step_presets import StepPreset, StepPresetPayload, default_step_presets
from ..core.structure_library import SavedStructure, default_structure_presets
from ..core.tech_bricks import TechBrick, default_tech_bricks
from .deps import get_current_user
from .keyed_resource import list_three_buckets, reject_duplicate, require_existing

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


class EntityTrackingInput(BaseModel):
    sample_id: str | None = None
    location: str | None = None


class LaunchExperienceRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    title: str
    intent: str
    hypothesis: str | None = None
    objectives: list[ObjectiveInput] = []
    # required on a brand-new launch (see launch_experience below) ; optional when evolving, where
    # it's only needed to fix forward an experience whose lineage never got one (see evolve_experience).
    entities: list[EntityTrackingInput] = []
    new_branch: str | None = None  # only meaningful when evolving: fork instead of continuing
    # answers to the project's active commit form (spectre.core.intent_forms), if one is
    # configured - re-asked on every real launch/evolution, unlike metadata/tags/evidence which
    # lightweight evolutions (conclure/preuves/etiquettes...) simply carry forward unchanged.
    form_answers: dict[str, Any] = {}


class CampaignPreviewRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    plan: structures.VariantPlan


class LaunchCampaignRequest(CampaignPreviewRequest):
    title: str
    intent: str
    hypothesis: str | None = None
    objectives: list[ObjectiveInput] = []
    entities: list[EntityTrackingInput] = []  # at least one (the reference sample) is required
    form_answers: dict[str, Any] = {}
    # when the campaign is built from an existing version (« partir d'une ref » / « continuer ») it
    # branches off that commit so the lineage/baseline link is kept, exactly like an évolution -
    # instead of starting a disconnected new branch.
    from_ref: str | None = None
    new_branch: str | None = None  # only meaningful with from_ref: name the forked branch


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


def _form_validation_error(exc: "follow.FormValidationError") -> HTTPException:
    """A commit form's own errors are already a list of specific, user-facing messages ("operator
    (Opérateur) est obligatoire") - meant, per its own docstring, to eventually drive a form UI
    that shows every invalid field at once rather than one at a time. Surfaced as a structured
    422 rather than folded into the generic FollowError->400 translation below.
    """
    return HTTPException(status_code=422, detail={"message": "Réponses au formulaire d'intention invalides.", "errors": exc.errors})


def _ref_the_first_experience(repo: "follow.Repository", experiment: "follow.Experiment") -> None:
    """A brand-new project has no ref yet to start from - so its very first experience becomes
    one automatically (the default "ref vX.Y.Z" name), rather than leaving every project stuck
    with nothing to feature in "Partir d'une ref" until someone remembers to tag one by hand.
    """
    if len(repo) == 1:
        refs.create_ref(repo, experiment.id)


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
    return [m.model_dump(mode="json") for m in structures.picker_materials()]


@router.get("/{slug}/recettes")
def list_recipes(project: Project = Depends(require_role("viewer"))) -> dict:
    """The named deposition/etch recipes a step can pick from - mode/angle/selectivity live on
    the recipe (see :mod:`structureforge.core.recipes`), not on the step itself.
    """
    recipes = structures.recipes_library()
    return {
        "deposition": [r.model_dump(mode="json") for r in recipes.deposition.values()],
        "etch": [r.model_dump(mode="json") for r in recipes.etch.values()],
    }


class StepPresetInput(BaseModel):
    name: str
    payload: StepPresetPayload
    notes: str | None = None
    partagee: bool = False


def _step_preset_store(project: Project, partagee: bool):
    return projects.get_shared_step_preset_store() if partagee else projects.get_step_preset_store(project.slug)


def _step_preset_payload(preset: StepPreset, scope: str) -> dict:
    return {**preset.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/presets-etapes")
def list_step_presets(project: Project = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        projects.get_step_preset_store(project.slug),
        projects.get_shared_step_preset_store(),
        default_step_presets(),
        _step_preset_payload,
    )


@router.post("/{slug}/presets-etapes", status_code=201)
def create_step_preset(body: StepPresetInput, project: Project = Depends(require_role("editor"))) -> dict:
    store = _step_preset_store(project, body.partagee)
    reject_duplicate(store, body.name, message=f"Un préset nommé {body.name!r} existe déjà dans cette bibliothèque.")
    preset = StepPreset(
        name=body.name,
        payload=body.payload,
        notes=body.notes,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(preset)
    return list_step_presets(project)


@router.put("/{slug}/presets-etapes/{name}")
def update_step_preset(
    name: str, body: StepPresetInput, partagee: bool = False, project: Project = Depends(require_role("editor"))
) -> dict:
    store = _step_preset_store(project, partagee)
    existing = require_existing(store, name, message=f"Préset {name!r} introuvable.")
    preset = StepPreset(name=body.name, payload=body.payload, notes=body.notes, created_at=existing.created_at)
    store.rename(name, preset)
    return list_step_presets(project)


@router.delete("/{slug}/presets-etapes/{name}")
def delete_step_preset(name: str, partagee: bool = False, project: Project = Depends(require_role("editor"))) -> dict:
    _step_preset_store(project, partagee).remove(name)
    return list_step_presets(project)


class SavedStructureInput(BaseModel):
    name: str
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    derived_from: str | None = None
    partagee: bool = False


def _saved_structure_store(project: Project, partagee: bool):
    return projects.get_shared_structure_store() if partagee else projects.get_structure_store(project.slug)


def _saved_structure_payload(structure: SavedStructure, scope: str) -> dict:
    return {**structure.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/structures-sauvegardees")
def list_saved_structures(project: Project = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        projects.get_structure_store(project.slug),
        projects.get_shared_structure_store(),
        default_structure_presets(),
        _saved_structure_payload,
    )


@router.post("/{slug}/structures-sauvegardees", status_code=201)
def create_saved_structure(body: SavedStructureInput, project: Project = Depends(require_role("editor"))) -> dict:
    store = _saved_structure_store(project, body.partagee)
    reject_duplicate(store, body.name, message=f"Une structure nommée {body.name!r} existe déjà dans cette bibliothèque.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        derived_from=body.derived_from,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(saved)
    return list_saved_structures(project)


@router.put("/{slug}/structures-sauvegardees/{name}")
def update_saved_structure(
    name: str, body: SavedStructureInput, partagee: bool = False, project: Project = Depends(require_role("editor"))
) -> dict:
    store = _saved_structure_store(project, partagee)
    existing = require_existing(store, name, message=f"Structure {name!r} introuvable.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        derived_from=existing.derived_from,
        created_at=existing.created_at,
    )
    store.rename(name, saved)
    return list_saved_structures(project)


@router.delete("/{slug}/structures-sauvegardees/{name}")
def delete_saved_structure(name: str, partagee: bool = False, project: Project = Depends(require_role("editor"))) -> dict:
    _saved_structure_store(project, partagee).remove(name)
    return list_saved_structures(project)


class TechBrickInput(BaseModel):
    name: str
    steps: list[ProcessStep]
    notes: str | None = None
    partagee: bool = False


def _tech_brick_store(project: Project, partagee: bool):
    return projects.get_shared_tech_brick_store() if partagee else projects.get_tech_brick_store(project.slug)


def _tech_brick_payload(brick: TechBrick, scope: str) -> dict:
    return {**brick.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/briques-technologiques")
def list_tech_bricks(project: Project = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        projects.get_tech_brick_store(project.slug),
        projects.get_shared_tech_brick_store(),
        default_tech_bricks(),
        _tech_brick_payload,
    )


@router.post("/{slug}/briques-technologiques", status_code=201)
def create_tech_brick(body: TechBrickInput, project: Project = Depends(require_role("editor"))) -> dict:
    store = _tech_brick_store(project, body.partagee)
    reject_duplicate(store, body.name, message=f"Une brique nommée {body.name!r} existe déjà dans cette bibliothèque.")
    brick = TechBrick(name=body.name, steps=body.steps, notes=body.notes, created_at=datetime.now(timezone.utc).isoformat())
    store.upsert(brick)
    return list_tech_bricks(project)


@router.put("/{slug}/briques-technologiques/{name}")
def update_tech_brick(
    name: str, body: TechBrickInput, partagee: bool = False, project: Project = Depends(require_role("editor"))
) -> dict:
    store = _tech_brick_store(project, partagee)
    existing = require_existing(store, name, message=f"Brique {name!r} introuvable.")
    brick = TechBrick(name=body.name, steps=body.steps, notes=body.notes, created_at=existing.created_at)
    store.rename(name, brick)
    return list_tech_bricks(project)


@router.delete("/{slug}/briques-technologiques/{name}")
def delete_tech_brick(name: str, partagee: bool = False, project: Project = Depends(require_role("editor"))) -> dict:
    _tech_brick_store(project, partagee).remove(name)
    return list_tech_bricks(project)


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
    entities = structures.clean_entity_entries(body.entities)
    if not any(e["sample_id"] for e in entities):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire pour lancer une expérience.",
        )

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
    builder.metadata["physical_tracking"] = entities
    if verification:
        builder.metadata["objective_verification"] = verification
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise _form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ref_the_first_experience(repo, experiment)

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
    entities = structures.clean_entity_entries(body.entities)
    if not any(e["sample_id"] for e in entities):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon de référence) est obligatoire pour lancer une campagne.",
        )

    try:
        result = structures.generate_campaign_variants(project.slug, body.substrate, body.steps, body.plan)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = projects.get_repository(project.slug)
    objectives, verification = split_objectives(body.objectives)
    lot = structures.ProcessLot(entries=result.entries)
    # exactly one tracking slot per variant (set_physical_tracking's own invariant) - the entities
    # supplied at launch fill the first slots, the rest start blank and get an id later as those
    # samples come off the campaign (see the atlas "Enregistrer les identifiants physiques" flow).
    padding = [{"sample_id": None, "location": None}] * max(0, len(result.entries) - len(entities))
    physical_tracking = (entities + padding)[: len(result.entries)]

    if body.from_ref:
        # A campaign started from an existing version keeps the lineage: repo.derive branches off
        # it and always adds the "baseline" reference, so the fiche's "versus the reference" views
        # and the graph link work exactly as for an évolution.
        try:
            repo.get(body.from_ref)
        except follow.ExperimentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="expérience de départ introuvable") from exc
        builder = repo.derive(
            body.from_ref,
            title=body.title,
            intent=body.intent,
            new_branch=body.new_branch or _unique_branch(repo, body.title),
            structure=lot,
            carry_steps=False,
            carry_objectives=not body.objectives,
            author=user.name,
            hypothesis=body.hypothesis,
        )
        builder.steps = follow_adapter.to_steps(body.steps)
        if body.objectives:
            builder.objectives = objectives
    else:
        builder = repo.new(
            branch=_unique_branch(repo, body.title),
            structure=lot,
            title=body.title,
            intent=body.intent,
            author=user.name,
            hypothesis=body.hypothesis,
            objectives=objectives,
            steps=follow_adapter.to_steps(body.steps),
        )
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps)
    builder.metadata["physical_tracking"] = physical_tracking
    builder.metadata["campaign_labels"] = result.labels
    builder.metadata["campaign_factor_labels"] = result.factor_labels
    builder.metadata["campaign_factor_values"] = result.factor_values
    if verification:
        builder.metadata["objective_verification"] = verification
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise _form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ref_the_first_experience(repo, experiment)

    return {"id": experiment.id, "branch": experiment.branch}
