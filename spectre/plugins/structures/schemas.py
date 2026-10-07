"""Request bodies of the structure routes, and the structure payloads an experiment is launched or
evolved with (:data:`StructurePayload`, one per kind of :mod:`spectre.plugins.structures.kinds`)."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from structureforge.process.steps import ProcessStep

from ...kernel.annotations import ImageAnnotation

from .campaigns import VariantPlan
from .simulation import DeclaredParam, LayerLabel, PresetOrigin, ProcessBrick, ProcessRecipes, SubstrateSpec


class ProcessInput(BaseModel):
    """A process to simulate: a substrate and its steps (``POST /api/simulations``).

    Each step may carry the ``id`` it was given (``st_<8 hex>``, see
    :func:`spectre.plugins.structures.simulation.settle_step_ids`): a ``ProcessStep`` ignores it, so
    it is read from the request itself, before validation, into :attr:`step_ids`."""

    substrate: SubstrateSpec
    steps: list[ProcessStep]
    # Spectre-only extra parameters attached per-step in the builder (see simulation.DeclaredParam)
    # - JSON object keys are always strings, converted to the step-index ints run_simulation wants
    # just before calling it.
    declared_params: dict[str, list[DeclaredParam]] = {}
    # the labels of the chosen steps, drawn beside the structure (see simulation.LayerLabel) - by
    # step index, like declared_params
    layer_labels: dict[str, LayerLabel] = {}
    # the bricks the steps belong to (see simulation.ProcessBrick) - by step index, like layer_labels
    bricks: list[ProcessBrick] = []
    # the process's own recipes (a selective etch defined in the builder, see simulation.ProcessRecipes)
    recipes: ProcessRecipes = Field(default_factory=ProcessRecipes)
    # the step preset each step was inserted from, if any (see simulation.PresetOrigin) - by step index
    preset_origins: dict[str, PresetOrigin] = {}
    _step_ids: list[str | None] = PrivateAttr(default_factory=list)

    @model_validator(mode="wrap")
    @classmethod
    def _read_step_ids(cls, data: Any, handler: Any) -> Any:
        model = handler(data)
        raw = data.get("steps") if isinstance(data, dict) else None
        if isinstance(raw, list):
            model._step_ids = [step.get("id") if isinstance(step, dict) and isinstance(step.get("id"), str) else None for step in raw]
        return model

    @property
    def step_ids(self) -> list[str | None]:
        """The id each step came with, in order (``None`` for a step sent without one)."""
        return [self._step_ids[i] if i < len(self._step_ids) else None for i in range(len(self.steps))]


class CampaignPreviewRequest(ProcessInput):
    """A process and the plan of its DOE campaign (``POST /api/campaign-previews``) - a factor can
    vary one of the declared parameters (``"declared:<name>"``)."""

    plan: VariantPlan


class CompositionRequest(BaseModel):
    """Combiner des études « au marché » (``POST /api/compositions``) : les procédés des sources, la
    principale d'abord, et, une fois choisi, l'index de la source de chaque ligne (``None`` : la
    brique n'est pas reprise ; ``choices`` absent : les choix par défaut)."""

    sources: list[ProcessInput] = Field(..., min_length=2, max_length=4)
    choices: list[int | None] | None = Field(None, max_length=200)


class StructureImageInput(BaseModel):
    image_id: str  # the id of an attachment uploaded with purpose=structure
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None
    annotations: list[ImageAnnotation] = []  # arrows and boxes drawn on it, in % of the picture


class StructureImagesInput(BaseModel):
    images: list[StructureImageInput]  # in reading order


class ProcessPayload(ProcessInput):
    kind: Literal["process"]


class CampaignPayload(CampaignPreviewRequest):
    kind: Literal["campaign"]


class ImagesPayload(StructureImagesInput):
    kind: Literal["images"]


class DeclaredWaferInput(BaseModel):
    label: str | None = None  # le nom de la variante, facultatif
    values: list[str] = []  # une valeur par colonne du split, dans leur ordre


class DeclaredPayload(BaseModel):
    """Une expérience sans structure : une description, un dessin collé facultatif, et le split
    déclaré - une colonne par chose qu'on change, une ligne par plaque (voir kinds.DeclaredStructure)."""

    kind: Literal["declared"]
    description: str | None = None
    images: list[StructureImageInput] = []
    factors: list[str] = []
    wafers: list[DeclaredWaferInput] = []


# The structure of an experiment, as a launch or an evolution sends it - told apart by ``kind``.
StructurePayload = Annotated[Union[ProcessPayload, ImagesPayload, CampaignPayload, DeclaredPayload], Field(discriminator="kind")]
