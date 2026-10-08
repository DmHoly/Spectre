"""The structure builder's own routes: the materials picker, the recipes, the simulation preview and
the preview of a DOE campaign - computed, nothing is stored. All simulation and rendering logic is
``structureforge``'s (see :mod:`spectre.plugins.structures.simulation`); launching an experiment
from a structure is the experiments plugin's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from . import campaigns, composition, rendering, simulation
from .schemas import CampaignPreviewRequest, CompositionRequest, ProcessInput

router = APIRouter(prefix="/api", tags=["structures"], dependencies=[Depends(current_user)])


@router.get("/materials")
def list_materials() -> list[dict]:
    return [m.model_dump(mode="json") for m in simulation.picker_materials()]


@router.get("/recipes")
def list_recipes() -> dict:
    """The named deposition/etch recipes of the library a step can pick from - mode/angle/selectivity
    live on the recipe (see :mod:`structureforge.core.recipes`), not on the step itself; a process
    may define its own besides (:class:`simulation.ProcessRecipes`).
    """
    recipes = simulation.recipes_library()
    return {
        "deposition": [r.model_dump(mode="json") for r in recipes.deposition.values()],
        "etch": [r.model_dump(mode="json") for r in recipes.etch.values()],
    }


@router.post("/simulations")
def simulate(body: ProcessInput) -> dict:
    """One frame (SVG, materials, layers) per step of the process, plus the colours of the
    materials - a 422 if StructureForge can't simulate it - and ``step_ids``, the id of each step:
    the one it came with, or a new one for a new step (the builder adopts it, it never makes one
    up - see :func:`simulation.settle_step_ids`). Each layer names the step that created it
    (``step_index``), and the SVGs carry the labels of ``layer_labels``, grouped by ``bricks``."""
    declared_params = simulation.declared_params_by_index(body.declared_params)
    labels = simulation.layer_labels_by_index(body.layer_labels, len(body.steps))
    bricks = simulation.checked_bricks(body.bricks, len(body.steps))
    result = simulation.simulate_process(body.substrate, body.steps, declared_params or None, body.recipes or None)
    return {
        **rendering.frames_payload(result.frames, result.materials, result.layer_origins, body.steps, declared_params, labels, bricks),
        "step_ids": simulation.settle_step_ids(body.step_ids),
    }


@router.post("/campaign-previews")
def preview_campaign(body: CampaignPreviewRequest) -> dict:
    """A preview of a DOE campaign: one simulated variant per combination of ``body.plan.factors``
    (fully crossed, at most :data:`campaigns.MAX_CAMPAIGN_ENTITIES`), plus the constant/varying
    split (``follow.doe.batch.analyze_batch``) - the "matrice de split", available before anyone
    commits to the campaign. Each factor names its step by ``step_id``, the id the step was sent
    with (``"substrate"`` for the substrate). Each variant's SVG carries the labels of
    ``layer_labels``, with its own values.
    """
    result = campaigns.generate_campaign_variants(
        body.substrate,
        body.steps,
        body.plan,
        simulation.declared_params_by_index(body.declared_params),
        body.step_ids,
        simulation.layer_labels_by_index(body.layer_labels, len(body.steps)),
        simulation.checked_bricks(body.bricks, len(body.steps)),
        body.recipes or None,
    )
    return {
        "svgs": result.svgs,
        "variation": result.variation.model_dump(mode="json"),
        "labels": result.labels,
        "factor_labels": result.factor_labels,
        "factor_values": result.factor_values,
    }


@router.post("/compositions")
def compose_structure(body: CompositionRequest) -> dict:
    """Combiner des études « au marché » (:mod:`.composition`) : les procédés des sources (la
    principale d'abord - celui d'une plaque d'une étude, d'une version de référence) et, une fois
    choisi, le choix de chaque ligne (sa source, l'étape qu'elle remplace) ; en retour, les lignes à
    choisir (une par étape, alignées par leur id puis leur nom, et le substrat) et le procédé
    assemblé. Rien n'est stocké."""
    choices = None if body.choices is None else [c.model_dump() if hasattr(c, "model_dump") else c for c in body.choices]
    return composition.compose(body.sources, choices)
