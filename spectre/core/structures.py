"""Bridges the structure-builder page to StructureForge: which materials and recipes a microproject can
draw on, and turning a substrate + step list into simulated frames the page can show. All the
physics stays in ``structureforge`` - a ``Deposition``/``Etch`` step names a recipe from the
recipe library by string key (mode/angle/selectivity live on the recipe, not the step), resolved
here at simulation time. This module only turns each ``Frame`` into ready-to-embed SVG via
``structureforge.presentation.svg.frame_to_svg``, so Spectre never draws a cross-section itself.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

import follow
from follow.doe.batch import BatchVariation, analyze_batch
from pydantic import BaseModel
from structureforge.adapters.follow_adapter import ProcessStructure, to_structure
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
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


def picker_materials() -> list[Material]:
    """The (deliberately short) list offered in the structure-builder's material dropdown - the
    editable root library (:func:`spectre.core.registry.registry_materials`,
    ``library/materiaux.yml``), nitride/semiconductor-oriented, not StructureForge's full ~46. The
    simulation still resolves *any* name (see :func:`materials_library`), so a structure that
    references a material later dropped from the picker keeps simulating.
    """
    from .registry import registry_materials

    return registry_materials()


def materials_library(*extra_names: str) -> MaterialLibrary:
    """StructureForge's full default library, with the editable root library
    (:func:`spectre.core.registry.registry_materials`) merged on top - so a root entry can add a
    material StructureForge lacks (GZO, AlCu) or recolor one - plus any dynamically-composed III-N
    material (``In{x:.2f}Ga{1-x:.2f}N`` / ``Al{y:.2f}Ga{1-y:.2f}N`` - see
    :func:`_graded_nitride_material`) named in ``extra_names``. A graded composition, picked via the
    structure-builder's "préciser le taux" field, is recreated on the fly from its own
    self-describing name (:func:`structureforge.core.materials.indium_gan`/``aluminum_gan``) instead
    of needing to be registered first. Callers pass every material name a request actually
    references (substrate, step fields, already-flattened layers...) so an unrecognized *plain* name
    still fails simulation the same way it always has - only names matching the graded-composition
    pattern are synthesized.
    """
    from .registry import registry_materials

    library = default_library().with_materials(*registry_materials())
    graded = [_graded_nitride_material(name) for name in extra_names if name not in library]
    resolved = [material for material in graded if material is not None]
    return library.with_materials(*resolved) if resolved else library


_GRADED_NITRIDE_RE = re.compile(r"^(In|Al)(\d\.\d{2})Ga\d\.\d{2}N$")


def _graded_nitride_material(name: str) -> Material | None:
    """Recompose the :class:`Material` a graded name like ``"In0.20Ga0.80N"`` encodes, by calling
    the same factory (:func:`structureforge.core.materials.indium_gan`/``aluminum_gan``) that
    produces that exact name - or ``None`` if ``name`` doesn't match the pattern at all, so callers
    can pass through arbitrary step field values (step names, recipe names...) unfiltered.
    """
    match = _GRADED_NITRIDE_RE.match(name)
    if not match:
        return None
    symbol, fraction_str = match.group(1), match.group(2)
    factory = indium_gan if symbol == "In" else aluminum_gan
    material = factory(float(fraction_str))
    return material if material.name == name else None


def _material_names_in_steps(steps: list[ProcessStep]) -> set[str]:
    """Every material name any step references - ``material``/``material_c``/``material_m``/
    ``material_sp``/``seed_materials``, whatever fields the step's own kind happens to expose -
    collected generically from each step's fields rather than a hardcoded per-kind list, so a
    future material-bearing field on any step kind is picked up without needing a change here.
    """
    names: set[str] = set()
    for step in steps:
        for field_name in type(step).model_fields:
            value = getattr(step, field_name, None)
            if isinstance(value, str):
                names.add(value)
            elif isinstance(value, list):
                names.update(v for v in value if isinstance(v, str))
    return names


def _material_names_in_layers(layers: list[Any]) -> set[str]:
    return {layer.material for layer in layers}


_INGAN_RE = re.compile(r"^In\d\.\d{2}Ga\d\.\d{2}N$")
_ALGAN_RE = re.compile(r"^Al\d\.\d{2}Ga\d\.\d{2}N$")


def _expand_seed_material_aliases(steps: list[ProcessStep], substrate_material: str) -> list[ProcessStep]:
    """A growth step's ``seed_materials`` (SAG selectivity) matches a layer *by exact name*, but
    InGaN/AlGaN never exist as a plain name - they're always a graded composition (``In0.20Ga0.80N``
    …). So a user who writes ``InGaN`` as the seed gets *nothing* (the SAG match silently finds no
    seed and the growth is a no-op). Here, before simulating, the bare tokens ``InGaN`` / ``AlGaN``
    in any ``seed_materials`` list are expanded to every matching graded composition actually present
    in this process (substrate + every step's material fields) - so "grow selectively on InGaN"
    means "on any InGaN composition", which is what people expect. A token with no match anywhere is
    left as-is (same harmless no-op as before). Steps are copied, never mutated in place.
    """
    all_names = {substrate_material} | _material_names_in_steps(steps)
    alias = {
        "InGaN": sorted(n for n in all_names if _INGAN_RE.match(n)),
        "AlGaN": sorted(n for n in all_names if _ALGAN_RE.match(n)),
    }
    if not any(alias.values()):
        return steps

    def _expand(seeds: list[str]) -> list[str]:
        out: list[str] = []
        for seed in seeds:
            for name in alias.get(seed) or [seed]:
                if name not in out:
                    out.append(name)
        return out

    result: list[ProcessStep] = []
    for step in steps:
        seeds = getattr(step, "seed_materials", None)
        if isinstance(seeds, list) and any(s in alias for s in seeds):
            result.append(step.model_copy(update={"seed_materials": _expand(seeds)}))
        else:
            result.append(step)
    return result


def recipes_library() -> RecipeLibrary:
    """StructureForge's default recipes plus any extra ones from the editable root library
    (``library/recettes.yml`` via :func:`spectre.core.registry.registry_recipes`) - where a
    selective etch (etch only Al2O3, say) is defined, since a recipe carries the whole
    selectivity table and a step/preset only names one.
    """
    from .registry import registry_recipes

    deposition, etch = registry_recipes()
    base = default_recipes()
    return base.with_recipes(deposition=deposition, etch=etch) if (deposition or etch) else base


def run_simulation(slug: str, substrate: SubstrateSpec, steps: list[ProcessStep]) -> tuple[Geometry, list[Frame], MaterialLibrary]:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) for a caller that needs them for
    more than just a preview (e.g. to commit the result as a Follow experiment). ``slug`` is kept
    in the signature even though every microproject shares the same material/step/recipe physics now -
    callers already pass it, and a microproject-specific material library is a plausible future need.
    """
    steps = _expand_seed_material_aliases(steps, substrate.material)
    materials = materials_library(substrate.material, *_material_names_in_steps(steps))
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

    materials = materials_library(*_material_names_in_layers(process_structure.layers))
    return _svg_for_process_structure(process_structure, {m.name: m.color for m in materials})


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
    names = {name for entry in lot.entries for name in _material_names_in_layers(entry.layers)}
    material_colors = {m.name: m.color for m in materials_library(*names)}
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
