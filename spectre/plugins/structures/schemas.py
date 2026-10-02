"""Request bodies shared by the structure routes and the experiment launches built on them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from structureforge.process.steps import ProcessStep

from .campaigns import VariantPlan
from .simulation import DeclaredParam, SubstrateSpec


class NewStructureRequest(BaseModel):
    substrate: SubstrateSpec
    steps: list[ProcessStep]
    # Spectre-only extra parameters attached per-step in the builder (see simulation.DeclaredParam)
    # - JSON object keys are always strings, converted to the step-index ints run_simulation wants
    # just before calling it.
    declared_params: dict[str, list[DeclaredParam]] = {}


class StructureImageInput(BaseModel):
    image_id: str  # returned by POST /structures/images once the picture is uploaded
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None


class StructureImagesInput(BaseModel):
    images: list[StructureImageInput]  # in reading order


class CampaignPreviewRequest(BaseModel):
    substrate: SubstrateSpec
    steps: list[ProcessStep]
    plan: VariantPlan
    declared_params: dict[str, list[DeclaredParam]] = {}  # a factor can vary one of them ("declared:<name>")
