"""Request bodies of the structure routes, and the structure payloads an experiment is launched or
evolved with (:data:`StructurePayload`, one per kind of :mod:`spectre.plugins.structures.kinds`)."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field
from structureforge.process.steps import ProcessStep

from .campaigns import VariantPlan
from .simulation import DeclaredParam, SubstrateSpec


class ProcessInput(BaseModel):
    """A process to simulate: a substrate and its steps (``POST /api/simulations``)."""

    substrate: SubstrateSpec
    steps: list[ProcessStep]
    # Spectre-only extra parameters attached per-step in the builder (see simulation.DeclaredParam)
    # - JSON object keys are always strings, converted to the step-index ints run_simulation wants
    # just before calling it.
    declared_params: dict[str, list[DeclaredParam]] = {}


class CampaignPreviewRequest(ProcessInput):
    """A process and the plan of its DOE campaign (``POST /api/campaign-previews``) - a factor can
    vary one of the declared parameters (``"declared:<name>"``)."""

    plan: VariantPlan


class StructureImageInput(BaseModel):
    image_id: str  # the id of an attachment uploaded with purpose=structure
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None


class StructureImagesInput(BaseModel):
    images: list[StructureImageInput]  # in reading order


class ProcessPayload(ProcessInput):
    kind: Literal["process"]


class CampaignPayload(CampaignPreviewRequest):
    kind: Literal["campaign"]


class ImagesPayload(StructureImagesInput):
    kind: Literal["images"]


# The structure of an experiment, as a launch or an evolution sends it - told apart by ``kind``.
StructurePayload = Annotated[Union[ProcessPayload, ImagesPayload, CampaignPayload], Field(discriminator="kind")]
