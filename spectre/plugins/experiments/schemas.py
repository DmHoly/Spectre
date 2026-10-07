"""Request bodies of the experiments routes: creating a line of study (any kind of structure, from
scratch or from an existing version), evolving it, and the lightweight writes on its tip."""

from __future__ import annotations

from typing import Any, Literal

import follow
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..structures.schemas import StructureImageInput, StructurePayload
from .entities import MAX_FDL_PER_ENTITY, MAX_TRACKED_ENTITIES, EntityTrackingInput


class ObjectiveInput(BaseModel):
    name: str
    metric: str
    direction: Literal["maximize", "minimize", "target", "range", "observe"] = "observe"
    target: float | None = None
    tolerance: float | None = None
    rationale: str | None = None  # pourquoi cet objectif compte
    verification_method: str | None = None  # comment on prévoit de le vérifier


class FromVersion(BaseModel):
    """The version a new line of study starts from - the tip of ``experiment_id`` when
    ``version_id`` is left out. ``place`` : la plaque de cette version dont on part (son index dans
    ``physical_tracking`` - la variante d'une campagne), sur de nouvelles plaques : « depuis la
    meilleure plaque » ; la structure envoyée est celle de sa variante."""

    experiment_id: str
    version_id: str | None = None
    place: int | None = Field(None, ge=0, le=500)


class MergeSource(BaseModel):
    """One of the two studies a combination starts from - the tip of ``experiment_id`` when
    ``version_id`` is left out. A study of this microproject only: any other field (a
    ``microproject``...) is refused rather than ignored."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    version_id: str | None = None


class WaferOrigin(BaseModel):
    """The study version the wafers of a new line come from - its structure is theirs, as they are
    now : the tip of ``experiment_id`` when ``version_id`` is left out, in the microproject
    ``microproject`` (this one: the new line descends from it ; another one the caller is a member
    of: the origin is only recorded). Any other field is refused rather than ignored."""

    model_config = ConfigDict(extra="forbid")

    microproject: str = Field(..., max_length=120)
    experiment_id: str
    version_id: str | None = None


class ComparisonReference(BaseModel):
    """La plaque de comparaison d'une campagne sans plaque de référence dans son split : l'étude du
    µprojet la plus proche (la piste ``experiment_id``, à sa version ``version_id`` si donnée) et,
    au choix, la plaque de cette étude qui sert de comparaison (son lasermark). Seulement cité :
    rien n'est vérifié, l'étude a pu changer depuis."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(..., min_length=1, max_length=200)
    version_id: str | None = Field(None, max_length=200)
    sample_id: str | None = Field(None, max_length=120)


# La forme d'une origine de référence (plugin references, qui dépend d'experiments et non l'inverse) :
# le slug d'une référence et le numéro MAJEUR.MINEUR d'une de ses versions. experiments n'en vérifie
# que la forme ; une origine inconnue se lit telle quelle, sans erreur.
REFERENCE_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
REFERENCE_NUMBER_PATTERN = r"^[1-9][0-9]{0,4}\.[0-9]{1,5}$"


class ReferenceOrigin(BaseModel):
    """La version de référence dont part une nouvelle étude : ``{reference, version}`` (« 1.1 »)."""

    model_config = ConfigDict(extra="forbid")

    reference: str = Field(..., max_length=80, pattern=REFERENCE_SLUG_PATTERN)
    version: str = Field(..., max_length=12, pattern=REFERENCE_NUMBER_PATTERN)


class CompositionSource(BaseModel):
    """Une source d'une combinaison « au marché » : une étude de ce µprojet (``kind="study"`` : sa
    piste, sa version, la plaque - sa place - dont on reprend la structure) ou une version de
    référence (``kind="reference"`` : son slug et son numéro). ``label`` : ce que la fiche en dit."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["study", "reference"]
    label: str = Field(..., min_length=1, max_length=200)
    experiment_id: str | None = Field(None, max_length=200)
    version_id: str | None = Field(None, max_length=200)
    place: int | None = Field(None, ge=0, le=500)
    reference: str | None = Field(None, max_length=80, pattern=REFERENCE_SLUG_PATTERN)
    version: str | None = Field(None, max_length=12, pattern=REFERENCE_NUMBER_PATTERN)

    @model_validator(mode="after")
    def _named(self) -> "CompositionSource":
        if self.kind == "study" and not self.experiment_id:
            raise ValueError("Une étude source nomme sa piste (experiment_id).")
        if self.kind == "reference" and not (self.reference and self.version):
            raise ValueError("Une référence source nomme son slug et sa version.")
        return self


class CompositionBrick(BaseModel):
    """Une ligne d'une combinaison : la brique (son nom, ou « Substrat ») et la source d'où elle
    vient (son index dans ``sources`` ; ``None`` : pas reprise)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    source: int | None = Field(None, ge=0, le=3)


class CompositionOrigin(BaseModel):
    """Une étude combinée « au marché » : ses sources (la principale d'abord - la nouvelle étude en
    descend quand c'est une étude du µprojet) et, brique par brique, d'où vient chacune. Le
    constructeur a assemblé la structure (``POST /api/compositions``) ; ceci est ce que la fiche en
    retient, et les autres études sources sont reliées dans l'arbre."""

    model_config = ConfigDict(extra="forbid")

    sources: list[CompositionSource] = Field(..., min_length=2, max_length=4)
    bricks: list[CompositionBrick] = Field([], max_length=200)


class _Intention(BaseModel):
    """What a launch and an evolution ask again: the intention, the objectives, the entity and the
    answers to the microproject's intention form."""

    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experiment back in context (shown at the top of the fiche) -
    # None keeps the one already there (see service.apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    # the physical samples followed (one per variant of a campaign, any number of replicates for a
    # simple study) - optional at launch (a slot stays blank until associated with a real wafer),
    # inherited when left empty on an evolution
    entities: list[EntityTrackingInput] = Field([], max_length=MAX_TRACKED_ENTITIES)
    # the FDL of the study (its wafers are read from them) - None keeps those already there
    fdl: list[str] | None = Field(None, max_length=MAX_FDL_PER_ENTITY)
    form_answers: dict[str, Any] = {}


class CreateExperimentRequest(_Intention):
    """A new line of study: a structure (from scratch, from an existing version with
    ``from_version``, or from existing wafers with ``wafer_origin`` - the study they come from, the
    wafers being the ``entities``), or the combination of two studies of the microproject
    (``merge_of``, exactly two : the new line's structure is the combined one, so no ``structure``
    is sent)."""

    structure: StructurePayload | None = None
    # several wafers of a simple study (no variation) declared as exact repeats of the reference
    # structure - stored as Experiment.metadata["repeats"], shown on the split sheet
    repeats: bool = False
    # for a campaign, the variant (its index) whose wafer is the reference - a repeat of the
    # reference structure - or None when the split has none; then, optionally, the wafer of a nearby
    # study it is compared with. Ignored for anything but a campaign
    reference_place: int | None = None
    comparison_reference: ComparisonReference | None = None
    from_version: FromVersion | None = None
    wafer_origin: WaferOrigin | None = None
    merge_of: list[MergeSource] | None = Field(None, min_length=2, max_length=2)
    branch: str | None = None  # the name of the new line of study - from its title by default
    # la version de référence dont part l'étude (le constructeur l'a chargée) - reportée aux versions
    # suivantes et aux fourches ; sans elle, une fourche garde celle de sa source
    reference_origin: ReferenceOrigin | None = None
    # l'expérience prévisionnelle qu'on lance (plans.py) : elle cesse de l'être une fois l'étude créée
    plan_id: int | None = None
    # combinée « au marché » (plusieurs études et/ou une référence, brique par brique) : la structure
    # est celle assemblée et envoyée ; ceci dit d'où vient chaque brique
    composition: CompositionOrigin | None = None
    # une plaque de plus, à la fin du split : une répétition exacte de cette version de référence (la
    # dernière connue de la référence d'origine) - la plaque témoin, hors des variantes. La dernière
    # des ``entities`` est la sienne
    reference_repeat: ReferenceOrigin | None = None

    @model_validator(mode="after")
    def _structure_or_combination(self) -> "CreateExperimentRequest":
        if self.merge_of is None and self.structure is None:
            raise ValueError("Une structure est nécessaire (ou merge_of, pour combiner deux études).")
        if self.merge_of is not None and (self.structure is not None or self.from_version is not None):
            raise ValueError("Une combinaison (merge_of) ne prend ni structure ni from_version : sa structure est la structure combinée.")
        if self.wafer_origin is not None and (self.from_version is not None or self.merge_of is not None):
            raise ValueError("Une étude partie de plaques (wafer_origin) ne prend ni from_version ni merge_of : elle part de l'étude de ses plaques.")
        if self.composition is not None and (self.from_version is not None or self.merge_of is not None or self.wafer_origin is not None):
            raise ValueError("Une étude combinée (composition) part de ses sources : ni from_version, ni merge_of, ni wafer_origin.")
        if self.reference_repeat is not None and self.merge_of is not None:
            raise ValueError("Une combinaison (merge_of) ne prend pas de répétition de la référence.")
        return self


class EvolveRequest(_Intention):
    structure: StructurePayload  # process or images: a campaign is launched as a new line of study


class StructureImagesRequest(BaseModel):
    images: list[StructureImageInput]  # in reading order


class ObjectiveResultInput(BaseModel):
    objective: str
    status: Literal["met", "not_met", "partially_met", "inconclusive"]
    observed: follow.Quantity | None = None
    # les entrées du cahier de données qui appuient ce verdict (leurs ids ; le nom est celui du champ
    # de Follow, ``ObjectiveResult.evidence_ids``)
    evidence_ids: list[str] = []
    reasoning: str | None = None


class ConclusionRequest(BaseModel):
    status: Literal["concluded", "abandoned"] = "concluded"
    decision: Literal["promote", "branch", "replicate", "abandon", "inconclusive"] | None = None
    summary: str | None = None
    next_steps: str | None = None
    objective_results: list[ObjectiveResultInput] = []


class StatusRequest(BaseModel):
    # only the "in progress" states - moving to concluded/abandoned is PUT .../conclusion, which
    # also records the per-objective verdicts and the narrative. « hold » pauses the study.
    status: Literal["draft", "running", "hold"]
    hold_reason: str | None = None


class TagsRequest(BaseModel):
    tags: list[str]


class EntitiesRequest(BaseModel):
    entities: list[EntityTrackingInput] = Field(..., max_length=MAX_TRACKED_ENTITIES)
    # the FDL of the study - None keeps those already there, [] removes them
    fdl: list[str] | None = Field(None, max_length=MAX_FDL_PER_ENTITY)


class RefRequest(BaseModel):
    experiment_id: str
    version_id: str | None = None  # the tip of experiment_id when left out
    name: str | None = None  # a nickname ; « ref vX.Y.Z » when left blank


class RefChanges(BaseModel):
    name: str | None = None  # the new name ; left out, nothing changes



class PlanRequest(BaseModel):
    """An experiment planned from the microproject's tree (see :mod:`.plans`): a title, an intent and
    what it continues - some of ``parent``'s wafers (``same_wafers``, their lasermarks in ``wafers``)
    or new ones (``new_wafers``, the estimated ``wafer_count``) ; without ``parent``, a new root (new
    wafers only). ``parent_plan_id`` instead of ``parent``: it follows another planned experiment,
    what that one will give once launched (its wafers, if it names them). No structure, no split:
    those come when it is launched."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., max_length=200)
    intent: str = Field("", max_length=4000)
    parent: FromVersion | None = None
    parent_plan_id: int | None = None
    mode: Literal["same_wafers", "new_wafers"] = "new_wafers"
    wafers: list[str] = Field([], max_length=MAX_TRACKED_ENTITIES)
    wafer_count: int | None = Field(None, ge=1, le=MAX_TRACKED_ENTITIES)


class PlanUpdate(BaseModel):
    """What changes on a planned experiment. Its starting point stays unless ``parent`` or
    ``parent_plan_id`` is given - re-attaching it (a detached one, typically) under a version or
    another planned experiment ; both given as ``null``, it becomes a root."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, max_length=200)
    parent: FromVersion | None = None
    parent_plan_id: int | None = None
    intent: str | None = Field(None, max_length=4000)
    mode: Literal["same_wafers", "new_wafers"] | None = None
    wafers: list[str] | None = Field(None, max_length=MAX_TRACKED_ENTITIES)
    wafer_count: int | None = Field(None, ge=1, le=MAX_TRACKED_ENTITIES)


class AttachmentRequest(BaseModel):
    """Where a study that started from nothing is attached (see :mod:`.attachments`): a version of
    another study of the microproject - the tip of ``experiment_id`` when ``version_id`` is left out."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    version_id: str | None = None
