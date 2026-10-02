"""The structure builder's own routes: the materials picker, the recipes, the simulation preview and
the preview of a DOE campaign. All simulation and rendering logic is ``structureforge``'s (see
:mod:`spectre.plugins.structures.simulation`); launching an experience from a structure is the
experiments plugin's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import campaigns, rendering, simulation
from .schemas import CampaignPreviewRequest, NewStructureRequest

router = APIRouter(prefix="/api/microprojets", tags=["structures"])


@router.get("/{slug}/materials")
def list_materials(microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return [m.model_dump(mode="json") for m in simulation.picker_materials()]


@router.get("/{slug}/recettes")
def list_recipes(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """The named deposition/etch recipes a step can pick from - mode/angle/selectivity live on
    the recipe (see :mod:`structureforge.core.recipes`), not on the step itself.
    """
    recipes = simulation.recipes_library()
    return {
        "deposition": [r.model_dump(mode="json") for r in recipes.deposition.values()],
        "etch": [r.model_dump(mode="json") for r in recipes.etch.values()],
    }


@router.post("/{slug}/structures/simulate")
def simulate_structure(body: NewStructureRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    declared_params = simulation.declared_params_by_index(body.declared_params) or None
    try:
        _geometry, frames, materials = simulation.run_simulation(microproject.slug, body.substrate, body.steps, declared_params)
    except simulation.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return rendering.frames_payload(frames, materials)


@router.post("/{slug}/structures/variantes")
def preview_campaign(body: CampaignPreviewRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    """A preview of a DOE campaign: one simulated variant per combination of ``body.plan.factors``
    (fully crossed), plus the constant/varying split (``follow.doe.batch.analyze_batch``) - the
    "matrice de split", available before anyone commits to the campaign.
    """
    try:
        result = campaigns.generate_campaign_variants(
            microproject.slug, body.substrate, body.steps, body.plan, simulation.declared_params_by_index(body.declared_params)
        )
    except simulation.SimulationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "svgs": result.svgs,
        "variation": result.variation.model_dump(mode="json"),
        "labels": result.labels,
        "factor_labels": result.factor_labels,
        "factor_values": result.factor_values,
    }
