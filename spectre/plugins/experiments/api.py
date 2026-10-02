"""Experiment endpoints: wraps ``follow.storage.repository.Repository`` for one microproject. Deep
logic (commits, diffing, DOE) stays in ``follow``; turning a re-edited process into a new
committed version goes through ``structureforge.adapters.follow_adapter.derive_experiment`` (added
in this repository's StructureForge branch specifically for Spectre's "evolve" flow). The one
thing Follow deliberately doesn't know is what "structural" means for a StructureForge process
(a substrate + ordered ``ProcessStep``s) - that classification, and the X.Y.Z it produces, lives
in :mod:`spectre.plugins.experiments.versioning`, layered on top of Follow's plain commit chain.
This module otherwise only resolves which microproject's repository to use and translates errors
into HTTP responses.

``{ref}`` (an experiment id, a branch or a ref name - :meth:`follow.storage.repository.Repository.get`
resolves all three) is a single path segment: none of them ever contains a "/" (refs and branch
names typed by a user are refused with one, see :func:`spectre.plugins.experiments.refs.create_ref`
and :func:`spectre.plugins.experiments.service.require_branch_name`), so route order no longer
matters - a literal suffix after ``{ref}`` (``/process``, ``/timeline``, ``/conclure``...) can never
be swallowed by the bare "get one experience" route, whichever router registers it.

The fiche shows the preuves (evidence plugin, listed after this one), read from inside
:func:`_detail`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import follow
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from structureforge.adapters import follow_adapter

from ..accounts.deps import current_user
from ..accounts.service import User
from ..attachments import store as attachments
from ..microprojects import service as microprojects
from ..microprojects.deps import get_microproject as resolve_microproject
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from ..structures import campaigns, kinds, simulation
from ..structures.schemas import StructureImagesInput
from . import refs, versioning
from .entities import EntityTrackingInput, clean_entity_entries, has_tracked_physical_entity
from .lineage import lineage_graph
from .repository import CONCLUDED_STATUSES, HOLD_KEY, RUNNING_STATUSES, branch_tips, display_status, get_repository, hold_of
from .schemas import LaunchCampaignRequest, LaunchExperienceRequest, LaunchImageExperienceRequest
from .service import (
    CONTEXT_METADATA_KEY,
    apply_context,
    derive_branch,
    first_tracked_entity,
    form_validation_error,
    not_found,
    ref_the_first_experience,
    require_branch_name,
    require_title_and_intent,
    split_objectives,
    unique_branch,
)

router = APIRouter(prefix="/api/microprojets", tags=["experiments"])


def _same_drawn_structure(parent: Any, process: dict) -> bool:
    """Whether an evolution in the builder left a single drawn structure exactly as it was."""
    from structureforge.adapters.follow_adapter import ProcessStructure

    return parent.structure_type == ProcessStructure.registry_key() and versioning.structure_signature(parent.metadata) == process


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


class CombineRequest(BaseModel):
    other_id: str
    title: str
    intent: str


class TagsRequest(BaseModel):
    tags: list[str]


class StatusRequest(BaseModel):
    # only the "in progress" states - moving to concluded/abandoned goes through /conclure,
    # which also records the per-objective verdicts and the narrative. « hold » pauses the study
    # (spectre.plugins.experiments.repository.HOLD_KEY) - draft/running resume it.
    status: Literal["draft", "running", "hold"]
    reason: str | None = None  # why it is paused (« hold » only)


class CreateRefRequest(BaseModel):
    name: str | None = None


class PhysicalTrackingRequest(BaseModel):
    entities: list[EntityTrackingInput]


def _summary(experiment: Any) -> dict:
    return {
        "id": experiment.id,
        "title": experiment.title,
        "intent": experiment.intent,
        "status": display_status(experiment),
        "author": experiment.author,
        "created_at": experiment.created_at.isoformat(),
        "branch": experiment.branch,
        "tags": list(experiment.tags),
        # The list is where a microproject's studies are seen all at once - a concluded study's own
        # summary belongs here too, not just on its own fiche, so where it fits is clear without
        # opening it.
        "conclusion_summary": experiment.conclusion.summary,
    }


def _detail(experiment: Any, repo: Any = None) -> dict:
    from ..evidence.service import EVIDENCE_EXTRA_KEY, evidence_payload

    # Every experiment whose own parents include this one - i.e. a version derived from here.
    # More than one means this version is a fork point: two (or more) lines of work continued
    # from it independently. repo is optional (a caller without one, if any, just skips this).
    children = (
        [{"id": exp.id, "title": exp.title, "branch": exp.branch} for exp in repo if experiment.id in exp.parents]
        if repo is not None
        else []
    )
    # « continuée » : la même règle que le graphe de filiation (un nœud brouillon avec une suite)
    node = next((n for n in lineage_graph(repo)["nodes"] if n["id"] == experiment.id), None) if repo is not None else None
    continued_at = node["continued_at"] if node else None
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
        # short description putting the experience back in context (metadata - see service.apply_context)
        "context": experiment.metadata.get("context"),
        "status": display_status(experiment, continued=bool(continued_at)),
        "continued_at": continued_at,
        "hold": hold_of(experiment),
        "objectives": [o.model_dump(mode="json") for o in experiment.objectives],
        "objective_verification": experiment.metadata.get("objective_verification", {}),
        "conclusion": experiment.conclusion.model_dump(mode="json"),
        "references": [r.model_dump(mode="json") for r in experiment.references],
        "tags": list(experiment.tags),
        "ref_names": refs.ref_names_for(repo, experiment.id) if repo is not None else [],
        "structure_svg": kinds.render_structure_svg(experiment.structure_type, experiment.structure),
        "is_batch": experiment.structure_type == kinds.ProcessLot.registry_key(),
        # a structure given as pictures: [{image_id, kind, caption}, ...] in reading order - the page
        # shows each /pieces-jointes/{image_id} where a drawn structure shows structure_svg
        "structure_images": kinds.structure_images(experiment.structure_type, experiment.structure),
        "has_editable_process": "structureforge_process" in experiment.metadata,
        "evidence": [evidence_payload(e, experiment.metadata.get(EVIDENCE_EXTRA_KEY, {})) for e in experiment.evidence],
        "physical_tracking": experiment.metadata.get("physical_tracking", []),
        "attachments": experiment.metadata.get("attachments", []),
        # per preuve id: the links (folder, PowerPoint deck...) recorded with it - kept here rather
        # than on follow.Evidence, whose fields depend on the installed Follow version
        "evidence_links": experiment.metadata.get("evidence_links", {}),
        # the experience's data notebook: views on its plates' characterization data (see api.notebook)
        "data_notebook": experiment.metadata.get("data_notebook", []),
        "data_items": experiment.metadata.get("data_items", []),
        "form_answers": dict(experiment.form_answers),
    }


@router.get("/{slug}/experiences")
def list_experiences(
    status: str = "all", offset: int = 0, limit: int = 30, microproject: Microproject = Depends(require_role("viewer"))
) -> dict:
    """Newest first, paginated - mirrors the ``{items, total, offset, limit}`` shape
    ``follow/api/app.py``'s own ``/api/experiments`` already uses, since a microproject's history is
    exactly the kind of list that can outgrow "load everything at once" as it grows.
    """
    if status not in ("all", "running", "concluded"):
        raise HTTPException(status_code=422, detail="status doit être 'all', 'running' ou 'concluded'")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset doit être >= 0")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit doit être entre 1 et 200")
    wanted = RUNNING_STATUSES if status == "running" else CONCLUDED_STATUSES if status == "concluded" else None

    repo = get_repository(microproject.slug)
    matches = [exp for exp in branch_tips(repo) if wanted is None or exp.conclusion.status in wanted]
    matches.sort(key=lambda exp: exp.created_at, reverse=True)
    page = matches[offset : offset + limit]
    return {"items": [_summary(exp) for exp in page], "total": len(matches), "offset": offset, "limit": limit}


@router.get("/{slug}/filiation")
def microproject_lineage(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """The microproject's structural lineage as plain JSON - what the µprojet page's default
    view (a D3 git-like graph, see ``spectre/api/static/js/microprojet-graphe.js``) draws instead
    of embedding the older Plotly ``/graphe.html``. Unlike the fiche's own "versions" timeline
    (:func:`spectre.plugins.experiments.versioning.determine_keep_ids`, which also keeps every branch tip so
    "where things stand" is never hidden there), a branch tip is *not* kept here just for being
    the tip - only a genuine structural change creates a node (a root, a merge from ``/combiner``,
    or a commit that actually moved the process forward). Changing only the status, tags, or title
    of an otherwise-unchanged process (``/statut``, ``/etiquettes``, ``/conclure`` without editing
    the structure...) must update the existing node's displayed state in place, never spawn a new
    one - that's the whole point of a view meant to show "un µprojet = split de structure", not
    version noise.

    So each structural id's displayed status/title/conclusion comes from whichever commit is
    actually current for it: itself, if it's still a live tip, or - when exactly one still-live
    tip descends from it with no structural change since - that tip's own live state, with the
    node's ``id`` switched to the tip's so "Ouvrir la fiche"/"Continuer d'ici" always act on the
    real current experiment. The rare case of two tips sharing the same structural point without
    either having changed anything structural (a fork with no structural edit yet) is genuinely
    two lines of work already - both are kept as their own small nodes off that shared point
    rather than arbitrarily picking one.

    Each node also carries ``started_at`` (when that structurally distinct experiment was
    created), ``ended_at`` (when it was concluded or abandoned, ``None`` while it is still a
    draft or running) and ``continued_at`` (when its first child started, if any) - the elapsed
    time the graph shows under each node -, plus its tracked ``wafers`` (lasermarks) and the
    ``lots`` holding one of them: the two badges beside the node.
    """
    return lineage_graph(get_repository(microproject.slug))


@router.get("/{slug}/experiences/{ref}/process")
def experience_process(ref: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = get_repository(microproject.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
    process = experiment.metadata.get("structureforge_process")
    if process is None:
        raise HTTPException(status_code=404, detail="cette expérience n'a pas de procédé éditable enregistré")
    return process


@router.get("/{slug}/experiences/{ref}/timeline")
def experience_timeline(ref: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Two views of the same lineage. ``versions`` keeps only the commits that actually moved the
    process/structure forward (see :mod:`spectre.plugins.experiments.versioning`), each carrying its own X.Y.Z -
    the frise chronologique's everyday view. ``items`` is every commit in the branch (a tag, a
    piece of evidence, a title edit... included), version number and all, for the "historique
    complet" at the bottom of the fiche.
    """
    repo = get_repository(microproject.slug)
    try:
        history = repo.log(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    chronological = list(reversed(history))
    branch_versions = versioning.compute_branch_versions(chronological)
    items = [
        {
            "id": exp.id,
            "title": exp.title,
            "intent": exp.intent,
            "created_at": exp.created_at.isoformat(),
            "author": exp.author,
            "is_current": i == len(chronological) - 1,
            "version": branch_versions[exp.id]["version"],
            "change_level": branch_versions[exp.id]["level"],
        }
        for i, exp in enumerate(chronological)
    ]
    versions = [item for item in items if item["change_level"] != "none"]
    return {"items": items, "versions": versions}


@router.get("/{slug}/experiences/{ref}/diff")
def experience_diff(ref: str, against: str | None = None, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = get_repository(microproject.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

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
        before = repo.get(target)
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {"target": target, **diff.model_dump(mode="json")}
    # pictures: a plain-French summary instead of Follow's position-by-position entries
    summary = kinds.describe_image_changes(before.structure_type, before.structure, experiment.structure_type, experiment.structure)
    if summary is not None:
        payload["summary"] = summary
    return payload


@router.post("/{slug}/experiences/{ref}/evoluer", status_code=201)
def evolve_experience(
    ref: str,
    body: LaunchExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    try:
        geometry, _frames, _materials = simulation.run_simulation(microproject.slug, body.substrate, body.steps)
    except simulation.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
        builder = follow_adapter.derive_experiment(
            repo,
            ref,
            geometry,
            body.steps,
            title=body.title,
            intent=body.intent,
            new_branch=derive_branch(repo, parent, body.new_branch),
            author=user.name,
            hypothesis=body.hypothesis,
            carry_objectives=not body.objectives,
        )
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    builder.metadata = dict(parent.metadata)
    builder.metadata.pop(HOLD_KEY, None)  # a new version starts afresh, not paused
    # continuing an image-mode experience in the builder: its structure is drawn from now on
    builder.metadata.pop(kinds.IMAGE_REVISION_KEY, None)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    if body.objectives:
        objectives, verification = split_objectives(body.objectives)
        builder.objectives = objectives
        if verification:
            builder.metadata["objective_verification"] = verification
        else:
            builder.metadata.pop("objective_verification", None)
    builder.metadata["structureforge_process"] = simulation.process_metadata(
        body.substrate, body.steps, simulation.declared_params_by_index(body.declared_params)
    )
    # « Éditer la fiche » without touching the structure (a clearer intention, a context, one more
    # objective...) is still the same study: its status and conclusion stay - only a structure that
    # actually changed starts a new, unconcluded iteration.
    if _same_drawn_structure(parent, builder.metadata["structureforge_process"]):
        builder.conclusion = parent.conclusion
    # entities are usually inherited unchanged from the parent (physical_tracking rides along in
    # builder.metadata above) - body.entities only matters to fix forward a lineage that started
    # before this rule existed, or predates the entity ever being set (see has_tracked_physical_entity).
    if body.entities:
        builder.metadata["physical_tracking"] = clean_entity_entries(body.entities)
    apply_context(builder.metadata, body.context)
    if not has_tracked_physical_entity(builder.metadata):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire - ajoutez-en une sur la version actuelle avant de continuer.",
        )
    builder.form_answers = dict(body.form_answers)

    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette évolution - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/experiences/{ref}/evoluer-image", status_code=201)
def evolve_experience_with_image(
    ref: str,
    body: LaunchImageExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Continue an experience with a new structure given as pictures - from an image-mode one, or
    from one drawn in the builder (a campaign included: the new version follows a single sample).
    The évolution counterpart of ``launch_image_experience``: same lineage rules as
    ``evolve_experience`` (baseline link, same piste unless forked, intention re-asked, the rest
    carried over), a fresh image revision so it counts as a new structure version."""
    require_title_and_intent(body.title, body.intent)
    image = kinds.structure_image_from_input(microproject.slug, body.images)
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    entities = first_tracked_entity(clean_entity_entries(body.entities)) or first_tracked_entity(
        clean_entity_entries([EntityTrackingInput(**e) for e in parent.metadata.get("physical_tracking", [])])
    )
    if not entities:
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire - renseignez-la avant de continuer.",
        )

    builder = repo.derive(
        ref,
        title=body.title.strip(),
        intent=body.intent.strip(),
        new_branch=derive_branch(repo, parent, body.new_branch),
        structure=image,
        author=user.name,
        hypothesis=body.hypothesis or None,
        carry_objectives=not body.objectives,
        carry_steps=False,
    )
    builder.metadata = {
        k: v for k, v in parent.metadata.items() if k not in kinds.DRAWN_STRUCTURE_METADATA_KEYS and k != HOLD_KEY
    }
    same_pictures = kinds.is_image_structure(parent.structure_type) and image.model_dump()["images"] == kinds.structure_images(
        parent.structure_type, parent.structure
    )
    if same_pictures and parent.metadata.get(kinds.IMAGE_REVISION_KEY):
        # same pictures: the fiche was edited, not the structure - same version, same conclusion
        builder.conclusion = parent.conclusion
    else:
        builder.metadata[kinds.IMAGE_REVISION_KEY] = kinds.new_image_revision()
    builder.metadata["physical_tracking"] = entities
    apply_context(builder.metadata, body.context)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    if body.objectives:
        objectives, verification = split_objectives(body.objectives)
        builder.objectives = objectives
        if verification:
            builder.metadata["objective_verification"] = verification
        else:
            builder.metadata.pop("objective_verification", None)
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette évolution - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/experiences/{ref}/dessin", status_code=201)
def replace_structure_drawing(
    ref: str,
    body: StructureImagesInput,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Change the pictures of an image-mode experience - the whole set, in reading order: a
    cleaner PowerPoint drawing, the TEM cross-section once it exists, one more close-up, another
    order, a caption... Like tags, a lightweight evolution: same structure revision, so no new
    structure version and no new node on the µprojet's graph - the previous pictures stay on the
    previous version. A drawn structure changes through the builder instead."""
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
    if not kinds.is_image_structure(parent.structure_type):
        raise HTTPException(
            status_code=422,
            detail="Cette structure est dessinée dans le constructeur : modifiez-la avec « Enregistrer une évolution ».",
        )
    image = kinds.structure_image_from_input(microproject.slug, body.images)
    if image.model_dump()["images"] == kinds.structure_images(parent.structure_type, parent.structure):
        return {"id": parent.id}

    builder = repo.derive(
        ref,
        title=parent.title,
        intent=parent.intent,
        new_branch=derive_branch(repo, parent, None),
        structure=image,
        author=user.name,
        hypothesis=parent.hypothesis,
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    builder.conclusion = parent.conclusion
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer le nouveau dessin - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref}/conclure", status_code=201)
def conclude_experience(
    ref: str,
    body: ConcludeRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    if not has_tracked_physical_entity(parent.metadata):
        raise HTTPException(
            status_code=422,
            detail="Impossible de conclure : aucune entité physique (échantillon réel) n'a été renseignée sur cette expérience.",
        )

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
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.metadata.pop(HOLD_KEY, None)  # concluded: no longer paused
    builder.form_answers = dict(parent.form_answers)
    builder.tags = list(parent.tags)
    builder.evidence = list(parent.evidence)
    builder.conclude(
        status=body.status,
        decision=body.decision,
        summary=body.summary,
        next_steps=body.next_steps,
        objective_results=objective_results,
    )
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer cette conclusion - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref}/combiner", status_code=201)
def combine_experiences(
    ref: str,
    body: CombineRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Combine two lines of work into one experience - Follow's ``repo.merge()`` supports
    field-by-field conflict resolution (``take_structure``/``take_steps``), which is exactly the
    kind of technical detail Spectre's UI avoids, so this always keeps ``ref``'s structure and
    steps as-is and simply links the other experience in as a second parent, its history and
    evidence still reachable from there. Both sides must be the same kind of structure (a single
    experience can't combine with a campaign).
    """
    repo = get_repository(microproject.slug)
    try:
        a = repo.get(ref)
        b = repo.get(body.other_id)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
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
            branch=derive_branch(repo, a, None),
            author=user.name,
        )
    except follow.FollowError as exc:
        raise HTTPException(status_code=422, detail="Ces deux expériences ne peuvent pas être combinées.") from exc
    builder.metadata = dict(a.metadata)
    builder.metadata.pop(HOLD_KEY, None)
    builder.tags = list(a.tags)
    builder.form_answers = dict(a.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible de combiner ces expériences - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.post("/{slug}/experiences/{ref}/etiquettes", status_code=201)
def set_tags(
    ref: str,
    body: TagsRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Replace this experience's tag set. Like ``conclure``/``preuves``, this is a lightweight
    evolution - since committed experiences are immutable, "editing" the tags means recording a
    new version that carries the status, structure, and everything else unchanged.
    """
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    cleaned: list[str] = []
    for tag in body.tags:
        tag = tag.strip()
        if tag and tag not in cleaned:
            cleaned.append(tag)

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = cleaned
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer les étiquettes - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "tags": cleaned}


@router.post("/{slug}/experiences/{ref}/statut", status_code=201)
def set_status(
    ref: str,
    body: StatusRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Move a study between « brouillon » (draft) and « en cours » (running), pause it
    (« hold », with an optional reason) or resume it, or reopen a concluded one to « en cours » so
    its conclusion can be revised. Like ``etiquettes``/``preuves`` this records a new immutable
    version carrying everything else unchanged - only ``conclusion.status`` (and, when reopening,
    the cleared ``decided_at``) or the ``hold`` metadata differ; the per-objective results are kept
    as a starting point for the revised conclusion.
    """
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    if display_status(parent) == body.status:
        return {"id": parent.id, "status": body.status}
    if body.status == "hold" and parent.conclusion.status not in RUNNING_STATUSES:
        raise HTTPException(status_code=422, detail="Seule une étude en brouillon ou en cours peut être mise en pause.")

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.tags = list(parent.tags)
    builder.evidence = list(parent.evidence)
    if body.status == "hold":
        reason = (body.reason or "").strip()[:300] or None
        builder.metadata[HOLD_KEY] = {"since": datetime.now(timezone.utc).isoformat(), "by": user.name, "reason": reason}
        builder.conclusion = parent.conclusion
    else:
        builder.metadata.pop(HOLD_KEY, None)
        builder.conclusion = parent.conclusion.model_copy(update={"status": body.status, "decided_at": None})
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer le changement de statut - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "status": body.status}


@router.post("/{slug}/experiences/{ref}/entites", status_code=201)
def set_physical_tracking(
    ref: str,
    body: PhysicalTrackingRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Attach a physical identifier and storage location to each entity this experience tracks -
    a single sample for an ordinary experience, one per variant for a campaign
    (:class:`spectre.plugins.structures.kinds.ProcessLot`). Purely descriptive bookkeeping Follow has no
    field for, so like tags this rides in ``Experiment.metadata`` and, like ``etiquettes``, is a
    lightweight evolution: recording a new version that carries everything else unchanged.
    """
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    expected_count = kinds.entity_count(parent.structure_type, parent.structure)
    if len(body.entities) != expected_count:
        raise HTTPException(
            status_code=422,
            detail=f"il faut exactement {expected_count} entrée(s) (une par échantillon suivi par cette expérience)",
        )

    entities = clean_entity_entries(body.entities)

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = list(parent.tags)
    builder.metadata["physical_tracking"] = entities
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer le suivi physique - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "entities": entities}


@router.post("/{slug}/experiences/{ref}/pieces-jointes", status_code=201)
async def upload_attachment(
    ref: str,
    file: UploadFile = File(...),
    entity_index_raw: str | None = Form(None, alias="entity_index"),
    evidence_id: str | None = Form(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Attach a file (mesure, wafer map, photo...) to this experience, to one of the physical
    entities it tracks (``entity_index``, into that experience's current ``physical_tracking``
    list - the same addressing the atlas's entity nodes and :mod:`spectre.plugins.links.service` already use),
    or to one of its preuves (``evidence_id`` - typically a ``kind="image"`` preuve the client will
    then annotate, see :func:`update_evidence_annotations`). Omitting both means the attachment
    belongs to the study as a whole. Like tags/physical_tracking, this rides in
    ``Experiment.metadata`` and records a new version rather than mutating anything in place. The
    uploaded bytes themselves live separately (:func:`spectre.plugins.attachments.store.attachments_dir`),
    named by a fresh id rather than the uploaded filename so nothing here ever has to turn a
    user-supplied name into a safe path.
    """
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    entity_index: int | None = None
    if entity_index_raw not in (None, ""):
        try:
            entity_index = int(entity_index_raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="entity_index doit être un entier") from exc
        expected_count = kinds.entity_count(parent.structure_type, parent.structure)
        if entity_index < 0 or entity_index >= expected_count:
            raise HTTPException(status_code=422, detail="cette entité n'existe pas sur cette expérience")

    if evidence_id is not None and not any(e.id == evidence_id for e in parent.evidence):
        raise HTTPException(status_code=422, detail="preuve introuvable sur cette expérience")

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in attachments.ATTACHMENT_ALLOWED_TYPES:
        raise HTTPException(status_code=422, detail=f"type de fichier non autorisé : {content_type or 'inconnu'}")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="fichier vide")
    if len(contents) > attachments.ATTACHMENT_MAX_BYTES:
        raise HTTPException(status_code=422, detail="fichier trop volumineux (10 Mo maximum)")

    attachment_id = attachments.new_attachment_id()
    original_name = (file.filename or "fichier").strip() or "fichier"
    sidecar = {"filename": original_name, "content_type": content_type, "size": len(contents)}
    attachments.write(microproject.slug, attachment_id, contents, sidecar)

    record = {
        "id": attachment_id,
        "filename": original_name,
        "content_type": content_type,
        "size": len(contents),
        "entity_index": entity_index,
        "evidence_id": evidence_id,
        "uploaded_by": user.name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    attached = list(parent.metadata.get("attachments", [])) + [record]

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = list(parent.tags)
    builder.metadata["attachments"] = attached
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        attachments.remove(microproject.slug, attachment_id)
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        attachments.remove(microproject.slug, attachment_id)
        raise HTTPException(
            status_code=400, detail="Impossible d'enregistrer la pièce jointe - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id, "attachment": record}


@router.delete("/{slug}/experiences/{ref}/pieces-jointes/{attachment_id}")
def remove_attachment(
    ref: str,
    attachment_id: str,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Detach a file from this experience's current tip - a new version without it in the list,
    same as removing a tag. The uploaded file itself is left on disk: an older version of this
    experience may still list it in its own (immutable) metadata, and nothing else in this app
    deletes old history either.
    """
    repo = get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    existing = parent.metadata.get("attachments", [])
    remaining = [a for a in existing if a.get("id") != attachment_id]
    if len(remaining) == len(existing):
        raise HTTPException(status_code=404, detail="pièce jointe introuvable sur cette version")

    builder = repo.derive(
        ref, title=parent.title, intent=parent.intent, new_branch=derive_branch(repo, parent, None), author=user.name
    )
    builder.metadata = dict(parent.metadata)
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.conclusion = parent.conclusion
    builder.tags = list(parent.tags)
    builder.metadata["attachments"] = remaining
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(
            status_code=400, detail="Impossible de retirer la pièce jointe - rechargez la page et réessayez."
        ) from exc
    return {"id": experiment.id}


@router.get("/{slug}/experiences/{ref}/diff-externe")
def experience_diff_external(
    ref: str,
    autre_projet: str,
    autre_experience: str,
    microproject: Microproject = Depends(require_role("viewer")),
    user: User = Depends(current_user),
) -> dict:
    """Compare this experience's structure against one in a *different* microproject - Follow's own
    ``repo.diff`` only ever compares within one repository, so this calls
    ``follow.diff_structures`` directly on the two experiments' raw structure dicts instead.
    Requires at least read access to both microprojects - comparing against a microproject the caller can't
    see would leak its content through the diff.
    """
    other_microproject = resolve_microproject(autre_projet)
    role = microprojects.role_for(other_microproject.id, user.id)
    if role is None:
        raise HTTPException(status_code=403, detail="vous n'avez pas accès à cet autre projet")

    repo = get_repository(microproject.slug)
    other_repo = get_repository(other_microproject.slug)
    try:
        experiment = repo.get(ref)
        other_experiment = other_repo.get(autre_experience)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    base = {
        "target": other_experiment.id,
        "target_microproject": other_microproject.name,
        "target_title": other_experiment.title,
    }
    if kinds.is_image_structure(experiment.structure_type) or kinds.is_image_structure(other_experiment.structure_type):
        # a picture has no parameters to line up against anything - say so rather than list raw fields
        return {**base, "entries": [], "note": "Une des deux structures est donnée en images : pas de comparaison paramètre par paramètre possible."}
    diff = follow.diff_structures(experiment.structure, other_experiment.structure)
    return {**base, **diff.model_dump(mode="json")}


@router.get("/{slug}/experiences/{ref}/matrice")
def experience_batch(ref: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """The constant/varying split of a DOE campaign's variants (``follow.doe.batch.analyze_batch``,
    the same analysis Follow's own GUI calls "matrice de split") - only meaningful for an
    experience whose structure is a :class:`spectre.plugins.structures.kinds.ProcessLot`.
    """
    repo = get_repository(microproject.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
    if experiment.structure_type != kinds.ProcessLot.registry_key():
        raise HTTPException(status_code=400, detail="cette expérience n'est pas une campagne à plusieurs variantes")
    lot = kinds.ProcessLot.model_validate(experiment.structure)
    variation = campaigns.analyze_variants(lot.entries)
    payload = variation.model_dump(mode="json")

    # The atlas: one drawn cross-section per entity - StructureForge does the actual rendering
    # (kinds.render_lot_svgs), Spectre only lines them up.
    payload["svgs"] = kinds.render_lot_svgs(lot)

    # The generic diff Follow computes names raw structure paths (e.g. "layers[1].rings[0]..."),
    # which is exactly the internal jargon Spectre's UI avoids everywhere else. Since Spectre is
    # also the only thing that ever creates a ProcessLot (via the guided campaign builder - see
    # :mod:`spectre.plugins.structures.campaigns`), it already computed, in plain terms, what was varied at
    # launch time (`generate_campaign_variants`) and stashed it on the commit - surface that
    # (`factor_labels`/`factor_values`/`labels`) so the page can lead with it and keep the raw
    # path table as a secondary, opt-in detail rather than the headline.
    payload["factor_labels"] = experiment.metadata.get("campaign_factor_labels", [])
    payload["factor_values"] = experiment.metadata.get("campaign_factor_values", [])
    payload["factor_scales"] = experiment.metadata.get("campaign_factor_scales", [])
    payload["labels"] = experiment.metadata.get("campaign_labels") or [f"#{i + 1}" for i in range(variation.entity_count)]
    payload["physical_tracking"] = experiment.metadata.get("physical_tracking", [])
    return payload


@router.post("/{slug}/experiences/{ref}/ref", status_code=201)
def create_ref(
    ref: str,
    body: CreateRefRequest,
    microproject: Microproject = Depends(require_role("editor")),
) -> dict:
    """Tag this experience as a ref: a named, reusable starting point future experiences can fork
    off from over and over (see :mod:`spectre.plugins.experiments.refs`), rather than being just one more version
    among many. ``body.name`` is a nickname ("omega", "banane"...) - left blank, it defaults to
    "ref vX.Y.Z" using the version :mod:`spectre.plugins.experiments.versioning` already computes for it.
    """
    repo = get_repository(microproject.slug)
    try:
        return refs.create_ref(repo, ref, name=body.name)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
    except refs.InvalidRefNameError as exc:
        raise HTTPException(status_code=422, detail="Le nom d'une ref ne peut pas contenir « / ».") from exc
    except refs.RefNameTakenError as exc:
        raise HTTPException(status_code=409, detail=f"Le nom « {exc.name} » est déjà pris par une autre version ou branche.") from exc


@router.get("/{slug}/experiences/{ref}")
def get_experience(ref: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = get_repository(microproject.slug)
    try:
        experiment = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc
    return _detail(experiment, repo)


@router.delete("/{slug}/experiences/{ref}")
def delete_experience(ref: str, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    """Delete a whole line of work: this version and its earlier versions, back to the point where
    the lineage forks or another branch/ref still needs them. Follow has no delete of its own
    (experiments are immutable, content-addressed), so this rewrites the JSON store directly - and
    only ever removes versions that nothing *outside* the deleted set still points to (no other
    branch tip, no experiment derived from them). Refuses if this isn't the current tip of its
    piste, or if something forks off it.
    """
    repo = get_repository(microproject.slug)
    try:
        target = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise not_found(exc) from exc

    branch_name = target.branch
    if repo.branches.get(branch_name) != target.id:
        raise HTTPException(
            status_code=422, detail="Ce n'est pas la version courante de cette piste - supprimez d'abord ce qui en découle."
        )

    to_delete: list[str] = []
    cur: str | None = target.id
    while cur is not None:
        exp = repo.get(cur)
        derived_elsewhere = [e.id for e in repo if cur in e.parents and e.id not in to_delete]
        foreign_tips = [b for b, tip in repo.branches.items() if tip == cur and b != branch_name]
        if derived_elsewhere or foreign_tips:
            break
        to_delete.append(cur)
        cur = exp.parents[0] if exp.parents else None

    if not to_delete:
        raise HTTPException(status_code=422, detail="Des pistes découlent de cette étude - supprimez-les d'abord.")

    deleted = set(to_delete)
    for exp_id in to_delete:
        repo._objects.pop(exp_id, None)
    for name in [n for n, tip in list(repo._tags.items()) if tip in deleted]:
        repo._tags.pop(name, None)
    if cur is not None and repo._objects[cur].branch == branch_name:
        repo._branches[branch_name] = cur
    else:
        repo._branches.pop(branch_name, None)

    repo._store.write_refs(dict(repo._branches), dict(repo._tags))
    if repo.path is not None:
        for exp_id in to_delete:
            (repo.path / "objects" / f"{exp_id}.json").unlink(missing_ok=True)

    return {"deleted": list(to_delete), "count": len(to_delete), "branch_removed": branch_name not in repo.branches}


@router.post("/{slug}/experiences", status_code=201)
def launch_experience(
    body: LaunchExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    entities = clean_entity_entries(body.entities)
    if not any(e["sample_id"] for e in entities):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire pour lancer une expérience.",
        )

    try:
        geometry, _frames, _materials = simulation.run_simulation(microproject.slug, body.substrate, body.steps)
    except simulation.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = get_repository(microproject.slug)
    branch = unique_branch(repo, body.title)
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
    builder.metadata["structureforge_process"] = simulation.process_metadata(
        body.substrate, body.steps, simulation.declared_params_by_index(body.declared_params)
    )
    builder.metadata["physical_tracking"] = entities
    apply_context(builder.metadata, body.context)
    if verification:
        builder.metadata["objective_verification"] = verification
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ref_the_first_experience(repo, experiment)

    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/experiences/image", status_code=201)
def launch_image_experience(
    body: LaunchImageExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Launch an experience without the builder: its structure is given as pictures (see
    :class:`spectre.plugins.structures.kinds.StructureImage`). Same rules as any launch otherwise - a title,
    an intention and a physical entity are required, the microproject's intention form applies,
    and the very first experience of a microproject becomes its first ref."""
    require_title_and_intent(body.title, body.intent)
    entities = first_tracked_entity(clean_entity_entries(body.entities))
    if not entities:
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire pour lancer une expérience.",
        )
    image = kinds.structure_image_from_input(microproject.slug, body.images)

    repo = get_repository(microproject.slug)
    objectives, verification = split_objectives(body.objectives)
    builder = repo.new(
        branch=unique_branch(repo, body.title),
        structure=image,
        title=body.title.strip(),
        intent=body.intent.strip(),
        author=user.name,
        hypothesis=body.hypothesis or None,
        objectives=objectives,
    )
    builder.metadata[kinds.IMAGE_REVISION_KEY] = kinds.new_image_revision()
    builder.metadata["physical_tracking"] = entities
    apply_context(builder.metadata, body.context)
    if verification:
        builder.metadata["objective_verification"] = verification
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ref_the_first_experience(repo, experiment)
    return {"id": experiment.id, "branch": experiment.branch}


@router.post("/{slug}/experiences/campagne", status_code=201)
def launch_campaign(
    body: LaunchCampaignRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Commit a whole DOE campaign as one experience: a ``ProcessLot`` holding one flattened
    variant per combination of ``body.plan.factors`` (fully crossed), with ``body.steps`` (the
    reference process) as the shared protocol - the same "one experiment, many entities" shape
    ``follow.doe.batch``/``follow/api/app.py`` already use generically for any domain.
    """
    entities = clean_entity_entries(body.entities)
    if not any(e["sample_id"] for e in entities):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon de référence) est obligatoire pour lancer une campagne.",
        )

    declared_params = simulation.declared_params_by_index(body.declared_params)
    try:
        result = campaigns.generate_campaign_variants(microproject.slug, body.substrate, body.steps, body.plan, declared_params)
    except simulation.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = get_repository(microproject.slug)
    objectives, verification = split_objectives(body.objectives)
    lot = kinds.ProcessLot(entries=result.entries)
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
            new_branch=require_branch_name(body.new_branch) or unique_branch(repo, body.title),
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
            branch=unique_branch(repo, body.title),
            structure=lot,
            title=body.title,
            intent=body.intent,
            author=user.name,
            hypothesis=body.hypothesis,
            objectives=objectives,
            steps=follow_adapter.to_steps(body.steps),
        )
    builder.metadata["structureforge_process"] = simulation.process_metadata(body.substrate, body.steps, declared_params)
    builder.metadata["physical_tracking"] = physical_tracking
    if body.from_ref and body.context is None:
        previous_context = repo.get(body.from_ref).metadata.get(CONTEXT_METADATA_KEY)
        if previous_context:
            builder.metadata[CONTEXT_METADATA_KEY] = previous_context
    apply_context(builder.metadata, body.context)
    builder.metadata["campaign_labels"] = result.labels
    builder.metadata["campaign_factor_labels"] = result.factor_labels
    builder.metadata["campaign_factor_values"] = result.factor_values
    # how each factor's values were laid out ("log" for a doping sweep over decades...) so every
    # later view shows them the same way, plus the plan itself (step/field/values) for re-reading
    builder.metadata["campaign_factor_scales"] = [factor.scale for factor in body.plan.factors]
    builder.metadata["campaign_plan"] = body.plan.model_dump(mode="json")
    if verification:
        builder.metadata["objective_verification"] = verification
    builder.form_answers = dict(body.form_answers)
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ref_the_first_experience(repo, experiment)

    return {"id": experiment.id, "branch": experiment.branch}


@router.get("/{slug}/refs")
def list_refs(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Unlike ``/etiquettes``/``/preuves``, a ref isn't scoped to one experience: it can be forked
    from indefinitely, long after the experience it names has stopped being any branch's tip, and
    the point is to see every one of them - and how they connect to each other - across the whole
    microproject at once. So listing them, and their condensed ref-to-ref graph, live at the
    microproject level (see :mod:`spectre.plugins.experiments.refs`)."""
    repo = get_repository(microproject.slug)
    return {"items": refs.list_refs(repo)}


@router.get("/{slug}/refs/graphe")
def refs_graph(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Refs as central nodes and the condensed edges between them - see
    :func:`spectre.plugins.experiments.refs.ref_graph`: lets a caller navigate from ref to ref
    without drawing the whole lineage.
    """
    repo = get_repository(microproject.slug)
    return refs.ref_graph(repo)
