"""Bridges the structure-builder page to StructureForge: which materials and recipes a structure can
draw on, and turning a substrate + step list into simulated frames the page can show. All the
physics stays in ``structureforge`` - a ``Deposition``/``Etch`` step names a recipe from the
recipe library by string key (mode/angle/selectivity live on the recipe, not the step), resolved
here at simulation time. Turning each ``Frame`` into ready-to-embed SVG is
:mod:`spectre.plugins.structures.rendering`'s, through ``structureforge.presentation.svg.frame_to_svg``,
so Spectre never draws a cross-section itself.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from pydantic import BaseModel, Field
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
from structureforge.core.recipes import RecipeLibrary, default_recipes
from structureforge.core.traced import Traced
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry, LayerProvenance
from structureforge.process.simulate import Frame, SimulationError, simulate
from structureforge.process.steps import ProcessStep

from ...kernel.errors import InvalidInput

class SubstrateSpec(BaseModel):
    material: str
    domain_width: Length
    thickness: Length


class SimulationFailedError(InvalidInput):
    """A process StructureForge can't simulate (an unknown material, a step that doesn't apply...),
    or a campaign plan that can't be built - the request is what's wrong, hence a 422."""


class DeclaredParam(BaseModel):
    """A Spectre-only, freely-named parameter a user attaches to a step in the builder - a name,
    a value, and free-form "obtention" details (e.g. ``precursor="SiH4"``, ``flow_sccm=12``).
    Independent of whatever typed fields the step's own ``ProcessStep`` subclass exposes (those
    are frozen pydantic models from ``structureforge`` and are never touched), and never stored
    on the step itself - merged onto the resulting layer(s)' ``provenance`` after simulation (see
    :func:`run_simulation`), as a ``Traced.declared`` entry.
    """

    name: str
    value: Any
    obtention: dict[str, Any] = Field(default_factory=dict)


def picker_materials() -> list[Material]:
    """The (deliberately short) list offered in the structure-builder's material dropdown - the
    editable root library (:func:`spectre.plugins.structures.library_files.materials`,
    ``library/materiaux.yml``), nitride/semiconductor-oriented, not StructureForge's full ~46. The
    simulation still resolves *any* name (see :func:`materials_library`), so a structure that
    references a material later dropped from the picker keeps simulating.
    """
    from .library_files import materials

    return materials()


def materials_library(*extra_names: str) -> MaterialLibrary:
    """StructureForge's full default library, with the editable root library
    (:func:`spectre.plugins.structures.library_files.materials`) merged on top - so a root entry can add a
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
    from .library_files import materials

    library = default_library().with_materials(*materials())
    graded = [_graded_nitride_material(name) for name in extra_names if name not in library]
    resolved = [material for material in graded if material is not None]
    return library.with_materials(*resolved) if resolved else library


GRADED_NITRIDE_RE = re.compile(r"^(In|Al)(\d\.\d{2})Ga\d\.\d{2}N$")


def _graded_nitride_material(name: str) -> Material | None:
    """Recompose the :class:`Material` a graded name like ``"In0.20Ga0.80N"`` encodes, by calling
    the same factory (:func:`structureforge.core.materials.indium_gan`/``aluminum_gan``) that
    produces that exact name - or ``None`` if ``name`` doesn't match the pattern at all, so callers
    can pass through arbitrary step field values (step names, recipe names...) unfiltered.
    """
    match = GRADED_NITRIDE_RE.match(name)
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


def material_names_in_layers(layers: list[Any]) -> set[str]:
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
    (``library/recettes.yml`` via :func:`spectre.plugins.structures.library_files.recipes`) - where a
    selective etch (etch only Al2O3, say) is defined, since a recipe carries the whole
    selectivity table and a step/preset only names one.
    """
    from .library_files import recipes

    deposition, etch = recipes()
    base = default_recipes()
    return base.with_recipes(deposition=deposition, etch=etch) if (deposition or etch) else base


def _apply_declared_params(frames: list[Frame], declared_params: dict[int, list[DeclaredParam]]) -> None:
    """Merge user-declared parameters (see :class:`DeclaredParam`) onto the layer(s) each step
    actually produced. Walks frames in step order tracking how many layers existed before each
    one - a step that appended new layers (growth, deposition, lithography...) gets its declared
    params attached to exactly those new layers; a step that didn't append any (etch,
    planarization, flip, chemical...) is skipped, since there's no safe way to know which existing
    layer a new declared param should be attributed to.
    """
    prev_count = 0
    for frame in frames:
        # `simulate()` prepends an implicit frame 0 ("initial", the starting geometry) before any
        # real step - so a real step at `frame.step_index == i` (1-based there) is the user's step
        # `i - 1` (0-based, how `declared_params` is keyed). Frame 0 itself never has a step to
        # attach declared params to.
        params = declared_params.get(frame.step_index - 1) if frame.step_index > 0 else None
        new_layers = frame.layers[prev_count:] if len(frame.layers) > prev_count else []
        if params and new_layers:
            for layer in new_layers:
                if layer.provenance is None:
                    layer.provenance = LayerProvenance(step_kind=frame.step_kind, step_name=frame.step_name, parameters={})
                for param in params:
                    layer.provenance.parameters[param.name] = Traced.declared(param.value, **param.obtention)
        prev_count = len(frame.layers)


def run_simulation(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared_params: dict[int, list[DeclaredParam]] | None = None,
) -> tuple[Geometry, list[Frame], MaterialLibrary]:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) for a caller that needs them for
    more than just a preview (e.g. to commit the result as a Follow experiment). Every microproject
    shares the same material/step/recipe physics.

    ``declared_params`` (step_index -> extra parameters the user attached in the builder, see
    :class:`DeclaredParam`) is Spectre-only bookkeeping never seen by ``structureforge`` itself -
    it's merged onto the resulting layers' ``provenance`` after simulation succeeds.
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
    if declared_params:
        _apply_declared_params(frames, declared_params)
    return geometry, frames, materials


def declared_params_by_index(raw: dict[str, list[DeclaredParam]] | None) -> dict[int, list[DeclaredParam]]:
    """A request's ``declared_params`` (JSON object keys are always strings) keyed by step index,
    empty lists dropped."""
    return {int(k): v for k, v in (raw or {}).items() if v}


def declared_params_json(declared_params: dict[int, list[DeclaredParam]] | None) -> dict[str, list[dict[str, Any]]]:
    return {str(i): [p.model_dump(mode="json") for p in params] for i, params in sorted((declared_params or {}).items()) if params}


# -- l'identité des étapes -------------------------------------------------------------------------
#
# Chaque étape d'un procédé porte un id stable (``st_<8 hex>``), opaque : une donnée, un facteur de
# campagne la désignent par lui plutôt que par sa position, qu'une insertion décalerait. Jamais vu
# de StructureForge (un ``ProcessStep`` l'ignore) ni du versionnage : une étude range ses ids à
# part, sous :data:`STEP_IDS_METADATA_KEY`, dans l'ordre des étapes de ``structureforge_process``.

STEP_IDS_METADATA_KEY = "process_step_ids"
STEP_ID_RE = re.compile(r"^st_[0-9a-f]{8}$")


def new_step_id(taken: set[str] | frozenset[str] = frozenset()) -> str:
    """Un id d'étape neuf, absent de ``taken``."""
    while True:
        candidate = f"st_{secrets.token_hex(4)}"
        if candidate not in taken:
            return candidate


def settle_step_ids(requested: list[str | None]) -> list[str]:
    """L'id de chaque étape, dans l'ordre : celui reçu quand il a la bonne forme et n'a pas déjà
    servi plus haut (une étape dupliquée garde son id une seule fois), un neuf sinon - une étape
    sans id est une nouvelle étape."""
    taken = {step_id for step_id in requested if isinstance(step_id, str) and STEP_ID_RE.fullmatch(step_id)}
    settled: list[str] = []
    for step_id in requested:
        if isinstance(step_id, str) and STEP_ID_RE.fullmatch(step_id) and step_id not in settled:
            settled.append(step_id)
        else:
            fresh = new_step_id(taken)
            taken.add(fresh)
            settled.append(fresh)
    return settled


def process_metadata(
    substrate: SubstrateSpec, steps: list[ProcessStep], declared_params: dict[int, list[DeclaredParam]] | None = None
) -> dict[str, Any]:
    """The raw, re-editable process (substrate + typed steps) as plain JSON - stashed on the
    committed ``Experiment.metadata`` under this key, since the ``Structure`` Follow stores is the
    *flattened* result (see ``structureforge.adapters.follow_adapter.ProcessStructure``) and can't
    be turned back into an editable step list on its own. See :mod:`spectre.plugins.experiments.api` for
    where this is read back to pre-fill the builder when evolving an experiment.

    The steps' declared parameters (:class:`DeclaredParam` - never part of a ``ProcessStep``) ride
    along under ``"declared_params"``, keyed by step index - only when there are some, so a
    process without any keeps exactly its former shape (and :mod:`spectre.plugins.experiments.versioning` sees no
    spurious change on lineages recorded before they were kept).
    """
    process: dict[str, Any] = {
        "substrate": substrate.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in steps],
    }
    declared = declared_params_json(declared_params)
    if declared:
        process["declared_params"] = declared
    return process
