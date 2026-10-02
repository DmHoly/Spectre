"""Structure definition and launch: the materials picker, the simulation preview, and turning a
simulated process into a new tracked experience - or, without the builder at all, launching one whose
structure is just a picture (a PowerPoint schematic, a TEM cross-section: see
:class:`spectre.core.structures.StructureImage`). All simulation and rendering logic is
``structureforge``'s (see :mod:`spectre.core.structures`); Follow's part (committing the result) is
``structureforge.adapters.follow_adapter``, extended in this repository with ``build_experiment``
for exactly this "commit once fully formed" use.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal

import follow
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from structureforge.adapters import follow_adapter
from structureforge.process.steps import ProcessStep

from ..core import microprojects, refs, structures
from ..core.accounts import User
from ..core.permissions import require_role
from ..core.microprojects import Microproject
from ..core.step_presets import StepPreset, StepPresetPayload, default_step_presets
from ..core.structure_library import SavedStructure, default_structure_presets
from ..core.tech_bricks import TechBrick, default_tech_bricks
from .deps import get_current_user
from .keyed_resource import list_three_buckets, reject_duplicate, require_existing

router = APIRouter(prefix="/api/microprojets", tags=["structures"])


class NewStructureRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    # Spectre-only extra parameters attached per-step in the builder (see structures.DeclaredParam)
    # - JSON object keys are always strings, converted to the step-index ints run_simulation wants
    # just before calling it.
    declared_params: dict[str, list[structures.DeclaredParam]] = {}


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
    fdl: list[str] = []  # FDL (JIRA launch sheets) this wafer went through - see spectre.core.fdl


class LaunchExperienceRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    # required on a brand-new launch (see launch_experience below) ; optional when evolving, where
    # it's only needed to fix forward an experience whose lineage never got one (see evolve_experience).
    entities: list[EntityTrackingInput] = []
    new_branch: str | None = None  # only meaningful when evolving: fork instead of continuing
    # the steps' declared parameters (see structures.DeclaredParam), keyed by step index - kept in
    # the committed process metadata (structures.process_metadata) so an evolution gets them back
    declared_params: dict[str, list[structures.DeclaredParam]] = {}
    # answers to the microproject's active commit form (spectre.core.intent_forms), if one is
    # configured - re-asked on every real launch/evolution, unlike metadata/tags/evidence which
    # lightweight evolutions (conclure/preuves/etiquettes...) simply carry forward unchanged.
    form_answers: dict[str, Any] = {}


class StructureImageInput(BaseModel):
    image_id: str  # returned by POST /structures/images once the picture is uploaded
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None


class StructureImagesInput(BaseModel):
    images: list[StructureImageInput]  # in reading order


class LaunchImageExperienceRequest(BaseModel):
    """A launch (or an evolution, see ``experiments.evolve_experience_with_image``) whose structure is
    given as pictures instead of a simulated process - otherwise the same intention fields as
    :class:`LaunchExperienceRequest`."""

    images: list[StructureImageInput]
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    entities: list[EntityTrackingInput] = []
    new_branch: str | None = None  # evolution only: fork instead of continuing
    form_answers: dict[str, Any] = {}


class CampaignPreviewRequest(BaseModel):
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    plan: structures.VariantPlan
    declared_params: dict[str, list[structures.DeclaredParam]] = {}  # a factor can vary one of them ("declared:<name>")


class LaunchCampaignRequest(CampaignPreviewRequest):
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
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


def require_branch_name(name: str | None) -> str | None:
    """A piste name typed by the user (``new_branch``) - refused with a "/" in it, which would not
    fit in the single ``{ref}`` path segment every experience route uses (see
    :mod:`spectre.api.experiments`)."""
    if name and "/" in name:
        raise HTTPException(status_code=422, detail="Le nom de la piste ne peut pas contenir « / ».")
    return name


def _form_validation_error(exc: "follow.FormValidationError") -> HTTPException:
    """A commit form's own errors are already a list of specific, user-facing messages ("operator
    (Opérateur) est obligatoire") - meant, per its own docstring, to eventually drive a form UI
    that shows every invalid field at once rather than one at a time. Surfaced as a structured
    422 rather than folded into the generic FollowError->400 translation below.
    """
    return HTTPException(status_code=422, detail={"message": "Réponses au formulaire d'intention invalides.", "errors": exc.errors})


def _ref_the_first_experience(repo: "follow.Repository", experiment: "follow.Experiment") -> None:
    """A brand-new microproject has no ref yet to start from - so its very first experience becomes
    one automatically (the default "ref vX.Y.Z" name), rather than leaving every microproject stuck
    with nothing to feature in "Partir d'une ref" until someone remembers to tag one by hand.
    """
    if len(repo) == 1:
        refs.create_ref(repo, experiment.id)


STRUCTURE_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_IMAGE_ID_RE = re.compile(r"^att_[0-9a-f]{20}$")  # same ids as the attachments (served by /pieces-jointes/{id})


def structure_image_from_input(slug: str, items: list[StructureImageInput]) -> structures.StructureImage:
    """The :class:`~spectre.core.structures.StructureImage` a request points at - only once every
    picture really is an uploaded image of *this* microproject (each id is checked against the
    files on disk, never turned into a path from anything else)."""
    if not items:
        raise HTTPException(status_code=422, detail="Collez ou choisissez au moins une image de la structure.")
    if len(items) > structures.MAX_STRUCTURE_IMAGES:
        raise HTTPException(status_code=422, detail=f"{structures.MAX_STRUCTURE_IMAGES} images au maximum.")
    if len({item.image_id for item in items}) != len(items):
        raise HTTPException(status_code=422, detail="La même image figure deux fois.")
    pictures = []
    for item in items:
        uploaded_image(slug, item.image_id)
        caption = (item.caption or "").strip()[:200] or None
        pictures.append(structures.StructureImageItem(image_id=item.image_id, kind=item.kind, caption=caption))
    return structures.StructureImage(images=pictures)


def uploaded_image(slug: str, image_id: str) -> dict:
    """The sidecar (filename, content type, size...) of an image uploaded to *this* microproject
    (``POST /images`` or ``/structures/images``) - 422 unless the id really names one, checked
    against the files on disk, never turned into a path from anything else."""
    missing = HTTPException(status_code=422, detail="Image introuvable - collez-la ou choisissez-la à nouveau.")
    if not _IMAGE_ID_RE.fullmatch(image_id or ""):
        raise missing
    directory = microprojects.attachments_dir(slug)
    sidecar_path = directory / f"{image_id}.json"
    if not (directory / image_id).is_file() or not sidecar_path.is_file():
        raise missing
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if sidecar.get("content_type") not in structures.STRUCTURE_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Ce fichier n'est pas une image affichable (PNG, JPEG, GIF ou WebP).")
    return sidecar


CONTEXT_METADATA_KEY = "context"


def apply_context(metadata: dict, context: str | None) -> None:
    """Set (or clear, when blank) the experience's short context description in its metadata -
    Follow's Experiment has title/intent/hypothesis but nothing for « remettre en contexte ». ``None``
    leaves whatever the metadata already carries (an evolution keeps the previous version's)."""
    if context is None:
        return
    value = context.strip()[:2000]
    if value:
        metadata[CONTEXT_METADATA_KEY] = value
    else:
        metadata.pop(CONTEXT_METADATA_KEY, None)


def require_title_and_intent(title: str, intent: str) -> None:
    if not title.strip() or not intent.strip():
        raise HTTPException(status_code=422, detail="Le titre et l'intention sont obligatoires.")


def first_tracked_entity(entities: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """An image-mode experience follows exactly one sample - the first one actually named."""
    named = [e for e in entities if e["sample_id"]]
    return named[:1]


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
def list_materials(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return [m.model_dump(mode="json") for m in structures.picker_materials()]


@router.get("/{slug}/structures/intention-form")
def get_intention_form(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Libellés/placeholders/aides éditables de la section « Objectifs et intention » du
    constructeur de structure (``library/intention.yml``, voir
    :func:`spectre.core.registry.registry_intention_form`).
    """
    from ..core.registry import registry_intention_form

    return registry_intention_form()


@router.get("/{slug}/recettes")
def list_recipes(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
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


def _step_preset_store(microproject: Microproject, partagee: bool):
    return microprojects.get_shared_step_preset_store() if partagee else microprojects.get_step_preset_store(microproject.slug)


def _step_preset_payload(preset: StepPreset, scope: str) -> dict:
    return {**preset.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/presets-etapes")
def list_step_presets(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        microprojects.get_step_preset_store(microproject.slug),
        microprojects.get_shared_step_preset_store(),
        default_step_presets(),
        _step_preset_payload,
    )


@router.post("/{slug}/presets-etapes", status_code=201)
def create_step_preset(body: StepPresetInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _step_preset_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Un préset nommé {body.name!r} existe déjà dans cette bibliothèque.")
    preset = StepPreset(
        name=body.name,
        payload=body.payload,
        notes=body.notes,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(preset)
    return list_step_presets(microproject)


@router.put("/{slug}/presets-etapes/{name}")
def update_step_preset(
    name: str, body: StepPresetInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _step_preset_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Préset {name!r} introuvable.")
    preset = StepPreset(name=body.name, payload=body.payload, notes=body.notes, created_at=existing.created_at)
    store.rename(name, preset)
    return list_step_presets(microproject)


@router.delete("/{slug}/presets-etapes/{name}")
def delete_step_preset(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _step_preset_store(microproject, partagee).remove(name)
    return list_step_presets(microproject)


class SavedStructureInput(BaseModel):
    name: str
    substrate: structures.SubstrateSpec
    steps: list[ProcessStep]
    declared_params: dict[str, list[structures.DeclaredParam]] = {}
    derived_from: str | None = None
    partagee: bool = False


def _saved_structure_store(microproject: Microproject, partagee: bool):
    return microprojects.get_shared_structure_store() if partagee else microprojects.get_structure_store(microproject.slug)


def _saved_structure_payload(structure: SavedStructure, scope: str) -> dict:
    return {**structure.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/structures-sauvegardees")
def list_saved_structures(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        microprojects.get_structure_store(microproject.slug),
        microprojects.get_shared_structure_store(),
        default_structure_presets(),
        _saved_structure_payload,
    )


@router.post("/{slug}/structures-sauvegardees", status_code=201)
def create_saved_structure(body: SavedStructureInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _saved_structure_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Une structure nommée {body.name!r} existe déjà dans cette bibliothèque.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        declared_params=structures.declared_params_json(structures.declared_params_by_index(body.declared_params)),
        derived_from=body.derived_from,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(saved)
    return list_saved_structures(microproject)


@router.put("/{slug}/structures-sauvegardees/{name}")
def update_saved_structure(
    name: str, body: SavedStructureInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _saved_structure_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Structure {name!r} introuvable.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        declared_params=structures.declared_params_json(structures.declared_params_by_index(body.declared_params)),
        derived_from=existing.derived_from,
        created_at=existing.created_at,
    )
    store.rename(name, saved)
    return list_saved_structures(microproject)


@router.delete("/{slug}/structures-sauvegardees/{name}")
def delete_saved_structure(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _saved_structure_store(microproject, partagee).remove(name)
    return list_saved_structures(microproject)


class TechBrickInput(BaseModel):
    name: str
    steps: list[ProcessStep]
    declared_params: dict[str, list[structures.DeclaredParam]] = {}
    notes: str | None = None
    partagee: bool = False


def _tech_brick_store(microproject: Microproject, partagee: bool):
    return microprojects.get_shared_tech_brick_store() if partagee else microprojects.get_tech_brick_store(microproject.slug)


def _tech_brick_payload(brick: TechBrick, scope: str) -> dict:
    return {**brick.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/briques-technologiques")
def list_tech_bricks(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        microprojects.get_tech_brick_store(microproject.slug),
        microprojects.get_shared_tech_brick_store(),
        default_tech_bricks(),
        _tech_brick_payload,
    )


@router.post("/{slug}/briques-technologiques", status_code=201)
def create_tech_brick(body: TechBrickInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _tech_brick_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Une brique nommée {body.name!r} existe déjà dans cette bibliothèque.")
    brick = TechBrick(
        name=body.name,
        steps=body.steps,
        declared_params=structures.declared_params_json(structures.declared_params_by_index(body.declared_params)),
        notes=body.notes,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(brick)
    return list_tech_bricks(microproject)


@router.put("/{slug}/briques-technologiques/{name}")
def update_tech_brick(
    name: str, body: TechBrickInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _tech_brick_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Brique {name!r} introuvable.")
    brick = TechBrick(
        name=body.name,
        steps=body.steps,
        declared_params=structures.declared_params_json(structures.declared_params_by_index(body.declared_params)),
        notes=body.notes,
        created_at=existing.created_at,
    )
    store.rename(name, brick)
    return list_tech_bricks(microproject)


@router.delete("/{slug}/briques-technologiques/{name}")
def delete_tech_brick(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _tech_brick_store(microproject, partagee).remove(name)
    return list_tech_bricks(microproject)


@router.post("/{slug}/structures/simulate")
def simulate_structure(body: NewStructureRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    declared_params = structures.declared_params_by_index(body.declared_params) or None
    try:
        _geometry, frames, materials = structures.run_simulation(microproject.slug, body.substrate, body.steps, declared_params)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return structures.frames_payload(frames, materials)


@router.post("/{slug}/experiences", status_code=201)
def launch_experience(
    body: LaunchExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    entities = structures.clean_entity_entries(body.entities)
    if not any(e["sample_id"] for e in entities):
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire pour lancer une expérience.",
        )

    try:
        geometry, _frames, _materials = structures.run_simulation(microproject.slug, body.substrate, body.steps)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = microprojects.get_repository(microproject.slug)
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
    builder.metadata["structureforge_process"] = structures.process_metadata(
        body.substrate, body.steps, structures.declared_params_by_index(body.declared_params)
    )
    builder.metadata["physical_tracking"] = entities
    apply_context(builder.metadata, body.context)
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


@router.post("/{slug}/images", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Upload a picture ahead of the preuve that will show it (pasted or dropped in the preuve
    form) - same storage and rules as :func:`upload_structure_image`."""
    return await _store_uploaded_image(file, microproject, user, role="preuve")


@router.post("/{slug}/structures/images", status_code=201)
async def upload_structure_image(
    file: UploadFile = File(...),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Upload one picture of a structure (pasted, dropped or picked on the « structure en image »
    page, or when changing the pictures on a fiche) ahead of the launch that will use it - so the
    page can show it straight from the server and the launch itself stays plain JSON. Stored like
    an attachment (blob + JSON sidecar named by a fresh id, see
    :func:`spectre.core.microprojects.attachments_dir`), served by the same
    ``/pieces-jointes/{id}`` route. A picture no launch ends up using just stays there, like a
    detached attachment."""
    return await _store_uploaded_image(file, microproject, user, role="structure")


async def _store_uploaded_image(file: UploadFile, microproject: Microproject, user: User, *, role: str) -> dict:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in structures.STRUCTURE_IMAGE_TYPES:
        if content_type in ("image/tiff", "image/tif", "image/bmp"):
            detail = "Format non affichable par le navigateur - copiez l'image depuis votre logiciel puis collez-la (Ctrl+V), ou exportez-la en PNG."
        else:
            detail = f"Type de fichier non pris en charge ({content_type or 'inconnu'}) : une image PNG, JPEG, GIF ou WebP."
        raise HTTPException(status_code=422, detail=detail)
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Image vide.")
    if len(contents) > STRUCTURE_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=422, detail="Image trop volumineuse (10 Mo maximum).")

    image_id = f"att_{secrets.token_hex(10)}"
    directory = microprojects.attachments_dir(microproject.slug)
    filename = (file.filename or "structure").strip() or "structure"
    sidecar = {
        "filename": filename,
        "content_type": content_type,
        "size": len(contents),
        "role": role,
        "uploaded_by": user.name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    (directory / image_id).write_bytes(contents)
    (directory / f"{image_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return {
        "image_id": image_id,
        "url": f"/api/microprojets/{microproject.slug}/pieces-jointes/{image_id}",
        "filename": filename,
        "content_type": content_type,
        "size": len(contents),
    }


@router.post("/{slug}/experiences/image", status_code=201)
def launch_image_experience(
    body: LaunchImageExperienceRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    """Launch an experience without the builder: its structure is given as pictures (see
    :class:`spectre.core.structures.StructureImage`). Same rules as any launch otherwise - a title,
    an intention and a physical entity are required, the microproject's intention form applies,
    and the very first experience of a microproject becomes its first ref."""
    require_title_and_intent(body.title, body.intent)
    entities = first_tracked_entity(structures.clean_entity_entries(body.entities))
    if not entities:
        raise HTTPException(
            status_code=422,
            detail="Une entité physique (l'échantillon réel suivi) est obligatoire pour lancer une expérience.",
        )
    image = structure_image_from_input(microproject.slug, body.images)

    repo = microprojects.get_repository(microproject.slug)
    objectives, verification = split_objectives(body.objectives)
    builder = repo.new(
        branch=_unique_branch(repo, body.title),
        structure=image,
        title=body.title.strip(),
        intent=body.intent.strip(),
        author=user.name,
        hypothesis=body.hypothesis or None,
        objectives=objectives,
    )
    builder.metadata[structures.IMAGE_REVISION_KEY] = structures.new_image_revision()
    builder.metadata["physical_tracking"] = entities
    apply_context(builder.metadata, body.context)
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
def preview_campaign(body: CampaignPreviewRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    """A preview of a DOE campaign: one simulated variant per combination of ``body.plan.factors``
    (fully crossed), plus the constant/varying split (``follow.doe.batch.analyze_batch``) - the
    "matrice de split", available before anyone commits to the campaign.
    """
    try:
        result = structures.generate_campaign_variants(
            microproject.slug, body.substrate, body.steps, body.plan, structures.declared_params_by_index(body.declared_params)
        )
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
    microproject: Microproject = Depends(require_role("editor")),
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

    declared_params = structures.declared_params_by_index(body.declared_params)
    try:
        result = structures.generate_campaign_variants(microproject.slug, body.substrate, body.steps, body.plan, declared_params)
    except structures.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = microprojects.get_repository(microproject.slug)
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
            new_branch=require_branch_name(body.new_branch) or _unique_branch(repo, body.title),
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
    builder.metadata["structureforge_process"] = structures.process_metadata(body.substrate, body.steps, declared_params)
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
        raise _form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ref_the_first_experience(repo, experiment)

    return {"id": experiment.id, "branch": experiment.branch}
