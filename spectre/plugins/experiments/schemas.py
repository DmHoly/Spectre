"""Request bodies of the experiments routes: creating a line of study (any kind of structure, from
scratch or from an existing version), evolving it, and the lightweight writes on its tip."""

from __future__ import annotations

from typing import Any, Literal

import follow
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..structures.schemas import StructureImageInput, StructurePayload
from .entities import EntityTrackingInput


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
    ``version_id`` is left out."""

    experiment_id: str
    version_id: str | None = None


class MergeSource(BaseModel):
    """One of the two studies a combination starts from - the tip of ``experiment_id`` when
    ``version_id`` is left out. A study of this microproject only: any other field (a
    ``microproject``...) is refused rather than ignored."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    version_id: str | None = None


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
    # the physical samples followed (one per variant of a campaign) - inherited when left empty on
    # an evolution or a launch from an existing version
    entities: list[EntityTrackingInput] = []
    form_answers: dict[str, Any] = {}


class CreateExperimentRequest(_Intention):
    """A new line of study: a structure (from scratch, or from an existing version with
    ``from_version``), or the combination of two studies of the microproject (``merge_of``, exactly
    two : the new line's structure is the combined one, so no ``structure`` is sent)."""

    structure: StructurePayload | None = None
    from_version: FromVersion | None = None
    merge_of: list[MergeSource] | None = Field(None, min_length=2, max_length=2)
    branch: str | None = None  # the name of the new line of study - from its title by default
    # la version de référence dont part l'étude (le constructeur l'a chargée) - reportée aux versions
    # suivantes et aux fourches ; sans elle, une fourche garde celle de sa source
    reference_origin: ReferenceOrigin | None = None

    @model_validator(mode="after")
    def _structure_or_combination(self) -> "CreateExperimentRequest":
        if self.merge_of is None and self.structure is None:
            raise ValueError("Une structure est nécessaire (ou merge_of, pour combiner deux études).")
        if self.merge_of is not None and (self.structure is not None or self.from_version is not None):
            raise ValueError("Une combinaison (merge_of) ne prend ni structure ni from_version : sa structure est la structure combinée.")
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
    entities: list[EntityTrackingInput]


class RefRequest(BaseModel):
    experiment_id: str
    version_id: str | None = None  # the tip of experiment_id when left out
    name: str | None = None  # a nickname ; « ref vX.Y.Z » when left blank


class RefChanges(BaseModel):
    name: str | None = None  # the new name ; left out, nothing changes

