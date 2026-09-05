"""Bridges the structure-builder page to StructureForge: which materials and recipes a project can
draw on, and turning a substrate + step list into simulated frames the page can show. All the
physics stays in ``structureforge`` - a ``Deposition``/``Etch`` step names a recipe from the
recipe library by string key (mode/angle/selectivity live on the recipe, not the step), resolved
here at simulation time. This module only turns each ``Frame`` into ready-to-embed SVG via
``structureforge.presentation.svg.frame_to_svg``, so Spectre never draws a cross-section itself.
"""

from __future__ import annotations

import itertools
from typing import Any

import follow
from follow.doe.batch import BatchVariation, analyze_batch
from pydantic import BaseModel
from structureforge.adapters.follow_adapter import ProcessStructure, to_structure
from structureforge.core.materials import MaterialLibrary, default_library
from structureforge.core.recipes import RecipeLibrary, default_recipes
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry
from structureforge.presentation.svg import frame_to_svg
from structureforge.process.simulate import Frame, SimulationError, simulate
from structureforge.process.steps import ProcessStep


class ProcessLot(follow.Structure):
    """A Follow ``Structure`` holding several ``ProcessStructure`` variants (a DOE campaign's
    wafers, say) - the one Spectre-level type needed so Follow's generic batch/DOE tooling
    (``follow.doe.batch.analyze_batch``, ``follow.doe.design``) can work on structures built by
    StructureForge, which only ever models one geometry at a time. See :mod:`spectre.api.structures`
    for where variants are generated.
    """

    entries: list[ProcessStructure]


class SubstrateSpec(BaseModel):
    material: str
    domain_width: Length
    thickness: Length


class SimulationFailedError(Exception):
    pass


def materials_library() -> MaterialLibrary:
    return default_library()


def recipes_library() -> RecipeLibrary:
    return default_recipes()


def run_simulation(slug: str, substrate: SubstrateSpec, steps: list[ProcessStep]) -> tuple[Geometry, list[Frame], MaterialLibrary]:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) for a caller that needs them for
    more than just a preview (e.g. to commit the result as a Follow experiment). ``slug`` is kept
    in the signature even though every project shares the same material/step/recipe physics now -
    callers already pass it, and a project-specific material library is a plausible future need.
    """
    materials = materials_library()
    recipes = recipes_library()
    try:
        materials.get(substrate.material)
    except KeyError as exc:
        raise SimulationFailedError(str(exc)) from exc

    geometry = Geometry.substrate(substrate.material, substrate.domain_width.to_nm(), substrate.thickness.to_nm())
    try:
        frames = simulate(geometry, steps, materials, recipes)
    except SimulationError as exc:
        raise SimulationFailedError(str(exc)) from exc
    return geometry, frames, materials


def frames_payload(frames: list[Frame], materials: MaterialLibrary) -> dict[str, Any]:
    material_colors = {m.name: m.color for m in materials}
    return {
        "frames": [
            {
                "step_index": frame.step_index,
                "step_kind": frame.step_kind,
                "step_name": frame.step_name,
                "svg": frame_to_svg(frame, material_colors),
                # only the materials this particular frame actually shows - material_colors below
                # is the whole library (40+ entries), which would make a poor legend on its own.
                "materials": sorted({layer.material for layer in frame.layers}),
            }
            for frame in frames
        ],
        "material_colors": material_colors,
    }


CAMPAIGN_FIELD_LABELS = {"thickness": "Épaisseur", "depth": "Profondeur", "target_level": "Niveau cible"}


class VariantFactor(BaseModel):
    """One parameter to vary, at the step ``step_index``, across ``values`` - a numeric field
    (``thickness``, ``depth``, ``target_level`` - whatever the step carries as a ``Length``, named
    by ``field``, in that field's own unit)."""

    step_index: int
    field: str
    values: list[float]


class VariantPlan(BaseModel):
    """A DOE campaign plan: one or more factors, fully crossed - every combination of every
    factor's values becomes one entity (5 thicknesses x 3 angles = 15 entities), the same "full
    factorial" ``follow.doe.design.full_factorial`` offers for a plain ``Structure`` field, applied
    here to a process's *steps* instead (which ``follow.doe.design`` never varies directly). A full
    factorial is always statistically identifiable - every factor is crossed with every other by
    construction - so there is nothing to warn about, unlike a hand-rolled "diagonal" sweep.
    """

    factors: list[VariantFactor]


class CampaignVariants(BaseModel):
    """The result of :func:`generate_campaign_variants` in a shape both the preview endpoint and
    the launch-a-campaign endpoint can use directly.
    """

    entries: list[ProcessStructure]
    svgs: list[str]
    variation: BatchVariation
    labels: list[str]  # one combined, human label per entity - e.g. "10 · 20" for 2 factors
    factor_labels: list[str]  # one label per factor - e.g. "Épaisseur — Oxyde initial"
    factor_values: list[list[float]]  # per entity, the raw value of each factor, same order


def _format_value_label(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _step_with_value(step: ProcessStep, field: str, value: float) -> ProcessStep:
    current = getattr(step, field, None)
    if not isinstance(current, Length):
        numeric_fields = [name for name in type(step).model_fields if isinstance(getattr(step, name, None), Length)]
        raise SimulationFailedError(
            f"{field!r} n'est pas un paramètre numérique modifiable de cette étape "
            f"(champs disponibles : {numeric_fields!r})"
        )
    return step.model_copy(update={field: Length(value=value, unit=current.unit)})


def generate_campaign_variants(
    slug: str, substrate: SubstrateSpec, steps: list[ProcessStep], plan: VariantPlan
) -> CampaignVariants:
    """Re-simulate ``steps`` once per combination in the full cross of every factor's values,
    varying each factor's field on its step for that combination - everything else (substrate,
    every other step, every other field) held constant. Returns one flattened ``ProcessStructure``
    and one preview SVG per combination, plus Follow's own constant/varying split
    (``follow.doe.batch.analyze_batch``) so the "matrice de split" is available before anyone
    commits to the campaign, not only after.
    """
    if not plan.factors:
        raise SimulationFailedError("il faut au moins un paramètre à faire varier")
    for factor in plan.factors:
        if not factor.values:
            raise SimulationFailedError("il faut au moins une valeur pour chaque paramètre")
        if not (0 <= factor.step_index < len(steps)):
            raise SimulationFailedError("étape sélectionnée invalide")
        if not factor.field:
            raise SimulationFailedError("il faut choisir un paramètre à faire varier")

    def _factor_label(factor: "VariantFactor") -> str:
        step_name = steps[factor.step_index].name
        return f"{CAMPAIGN_FIELD_LABELS.get(factor.field, factor.field)} — {step_name}"

    factor_labels = [_factor_label(factor) for factor in plan.factors]

    entries: list[ProcessStructure] = []
    svgs: list[str] = []
    labels: list[str] = []
    factor_values: list[list[float]] = []
    for combo in itertools.product(*(factor.values for factor in plan.factors)):
        varied_steps = list(steps)
        for factor, value in zip(plan.factors, combo):
            varied_steps[factor.step_index] = _step_with_value(varied_steps[factor.step_index], factor.field, value)
        geometry, frames, materials = run_simulation(slug, substrate, varied_steps)
        entries.append(to_structure(geometry))
        material_colors = {m.name: m.color for m in materials}
        svgs.append(frame_to_svg(frames[-1], material_colors))
        labels.append(" · ".join(_format_value_label(v) for v in combo))
        factor_values.append(list(combo))

    variation = analyze_batch(entries)
    return CampaignVariants(
        entries=entries, svgs=svgs, variation=variation, labels=labels, factor_labels=factor_labels, factor_values=factor_values
    )


class _RenderableLayer:
    """Duck-types as the ``structureforge.geometry.engine.Layer`` that
    ``structureforge.presentation.svg.frame_to_svg`` expects (a ``material`` attribute plus a
    ``rings()`` method) - built from the *already-flattened* ``LayerSpec`` a committed
    ``ProcessStructure`` stores (``rings`` there is a plain field, not a method).
    """

    __slots__ = ("material", "_rings")

    def __init__(self, material: str, rings: list[dict]) -> None:
        self.material = material
        self._rings = rings

    def rings(self) -> list[dict]:
        return self._rings


def render_structure_svg(structure_type: str, structure_data: dict[str, Any]) -> str | None:
    """SVG for an already-committed experiment's current structure, reusing
    ``structureforge.presentation.svg.frame_to_svg`` on a synthetic single-frame ``Frame`` built
    from the stored, already-flattened layers. ``None`` for any structure type StructureForge
    doesn't know how to draw (the fiche just skips the diagram then) - a ``ProcessLot`` batch
    renders its first entry, the representative case a DOE campaign's constant/varying split
    (:func:`spectre.api.experiments`) already covers in full.
    """
    if structure_type == ProcessStructure.registry_key():
        process_structure = ProcessStructure.model_validate(structure_data)
    elif structure_type == ProcessLot.registry_key():
        lot = ProcessLot.model_validate(structure_data)
        if not lot.entries:
            return None
        process_structure = lot.entries[0]
    else:
        return None

    return _svg_for_process_structure(process_structure, {m.name: m.color for m in materials_library()})


def _svg_for_process_structure(process_structure: ProcessStructure, material_colors: dict[str, str]) -> str:
    frame = Frame(
        step_index=0,
        step_kind="structure",
        step_name="structure",
        layers=[_RenderableLayer(layer.material, layer.rings) for layer in process_structure.layers],
        domain_width_nm=process_structure.domain_width_nm,
    )
    return frame_to_svg(frame, material_colors)


def render_lot_svgs(lot: ProcessLot) -> list[str]:
    """One SVG per entity in a committed campaign - the "atlas": every variant drawn side by
    side, not just the reference one ``render_structure_svg`` shows on its own.
    """
    material_colors = {m.name: m.color for m in materials_library()}
    return [_svg_for_process_structure(entry, material_colors) for entry in lot.entries]


def clean_entity_entries(entities: list[Any]) -> list[dict[str, str | None]]:
    """Normalize a list of entity-tracking inputs (each with a ``sample_id``/``location``
    attribute) into the plain dict shape stored in ``Experiment.metadata["physical_tracking"]`` -
    blank strings become ``None``, the same cleanup ``spectre.api.experiments::set_physical_tracking``
    already applied locally before this was shared with the launch routes below.
    """

    def _clean(value: str | None) -> str | None:
        return value.strip() or None if value else None

    return [{"sample_id": _clean(e.sample_id), "location": _clean(e.location)} for e in entities]


def has_tracked_physical_entity(metadata: dict[str, Any]) -> bool:
    """Whether at least one physical entity (a real sample identifier, not just a blank tracking
    slot) has ever been recorded on this experience - every experience must be traceable to
    something physical, checked when it's created and enforced again before it can be concluded.
    """
    return any(entry.get("sample_id") for entry in metadata.get("physical_tracking", []))


def process_metadata(substrate: SubstrateSpec, steps: list[ProcessStep]) -> dict[str, Any]:
    """The raw, re-editable process (substrate + typed steps) as plain JSON - stashed on the
    committed ``Experiment.metadata`` under this key, since the ``Structure`` Follow stores is the
    *flattened* result (see ``structureforge.adapters.follow_adapter.ProcessStructure``) and can't
    be turned back into an editable step list on its own. See :mod:`spectre.api.structures` for
    where this is read back to pre-fill the builder when evolving an experiment.
    """
    return {
        "substrate": substrate.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in steps],
    }
