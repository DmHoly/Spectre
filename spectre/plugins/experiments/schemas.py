"""Request bodies of the experiments routes: creating a line of study (any kind of structure, from
scratch or from an existing version), evolving it, and the lightweight writes on its tip."""

from __future__ import annotations

from typing import Any, Literal

import follow
from pydantic import BaseModel

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
    structure: StructurePayload
    from_version: FromVersion | None = None
    branch: str | None = None  # the name of the new line of study - from its title by default


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


class MergeRequest(BaseModel):
    other_experiment_id: str


class RefRequest(BaseModel):
    experiment_id: str
    version_id: str | None = None  # the tip of experiment_id when left out
    name: str | None = None  # a nickname ; « ref vX.Y.Z » when left blank


class RefChanges(BaseModel):
    name: str | None = None  # the new name ; left out, nothing changes

