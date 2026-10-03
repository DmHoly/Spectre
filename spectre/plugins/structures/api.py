"""The structure builder's own routes: the materials picker, the recipes, the simulation preview and
the preview of a DOE campaign - computed, nothing is stored. All simulation and rendering logic is
``structureforge``'s (see :mod:`spectre.plugins.structures.simulation`); launching an experiment
from a structure is the experiments plugin's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from . import campaigns, rendering, simulation
from .schemas import CampaignPreviewRequest, ProcessInput

router = APIRouter(prefix="/api", tags=["structures"], dependencies=[Depends(current_user)])


@router.get("/materials")
def list_materials() -> list[dict]:
    return [m.model_dump(mode="json") for m in simulation.picker_materials()]


@router.get("/recipes")
def list_recipes() -> dict:
    """The named deposition/etch recipes a step can pick from - mode/angle/selectivity live on
    the recipe (see :mod:`structureforge.core.recipes`), not on the step itself.
    """
    recipes = simulation.recipes_library()
    return {
        "deposition": [r.model_dump(mode="json") for r in recipes.deposition.values()],
        "etch": [r.model_dump(mode="json") for r in recipes.etch.values()],
    }


@router.post("/simulations")
def simulate(body: ProcessInput) -> dict:
    """One frame (SVG, materials, layers) per step of the process, plus the colours of the
    materials - a 422 if StructureForge can't simulate it."""
    declared_params = simulation.declared_params_by_index(body.declared_params) or None
    _geometry, frames, materials = simulation.run_simulation(body.substrate, body.steps, declared_params)
    return rendering.frames_payload(frames, materials)


@router.post("/campaign-previews")
def preview_campaign(body: CampaignPreviewRequest) -> dict:
    """A preview of a DOE campaign: one simulated variant per combination of ``body.plan.factors``
    (fully crossed, at most :data:`campaigns.MAX_CAMPAIGN_ENTITIES`), plus the constant/varying
    split (``follow.doe.batch.analyze_batch``) - the "matrice de split", available before anyone
    commits to the campaign.
    """
    result = campaigns.generate_campaign_variants(
        body.substrate, body.steps, body.plan, simulation.declared_params_by_index(body.declared_params)
    )
    return {
        "svgs": result.svgs,
        "variation": result.variation.model_dump(mode="json"),
        "labels": result.labels,
        "factor_labels": result.factor_labels,
        "factor_values": result.factor_values,
    }
