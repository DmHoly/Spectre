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
import secrets
from enum import Enum
from typing import Any, Literal

import follow
from follow.core.errors import BatchShapeError
from follow.doe.batch import BatchVariation, analyze_batch
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from structureforge.adapters.follow_adapter import ProcessStructure, to_structure
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
from structureforge.core.recipes import RecipeLibrary, default_recipes
from structureforge.core.traced import Traced
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry, LayerProvenance
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


class StructureImageItem(BaseModel):
    """One picture of a :class:`StructureImage`: which uploaded image (a file of the microproject's
    attachments, see :func:`spectre.core.microprojects.attachments_dir`), what kind of picture it
    is, and an optional caption."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None


MAX_STRUCTURE_IMAGES = 12


class StructureImage(follow.Structure):
    """A structure given as pictures instead of being drawn step by step in the builder - a
    schematic pasted from PowerPoint, TEM/SEM cross-sections, a photo... several of them when one
    alone doesn't tell the whole story (the schematic + an overview cross-section + a close-up),
    in the order they should be read. Spectre knows nothing of the layers (no simulation, no
    per-step provenance, no campaign split). Changing the pictures is a lightweight evolution of
    the same experience (see ``spectre.api.experiments::replace_structure_drawing``); an actual
    change of structure is an evolution with new pictures (``evoluer-image``) - told apart for
    versioning by :data:`IMAGE_REVISION_KEY`, not by the pictures themselves.
    """

    images: list[StructureImageItem] = Field(min_length=1, max_length=MAX_STRUCTURE_IMAGES)

    @model_validator(mode="before")
    @classmethod
    def _single_image_shape(cls, data: Any) -> Any:
        # the very first version of this mode held one flat picture ({image_id, kind, caption})
        if isinstance(data, dict) and "image_id" in data and "images" not in data:
            return {"images": [data]}
        return data


# Types d'image acceptés pour une structure en image : ce que le navigateur sait afficher tel quel
# (un TIFF de microscope ne l'est pas - le coller depuis le logiciel, ou l'exporter en PNG).
# image/svg+xml volontairement absent, comme pour les pièces jointes (un SVG peut porter du script).
STRUCTURE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Metadata key holding the "which structure is this" token of an image-mode experience: set anew
# on a real launch/evolution, carried unchanged by every lightweight evolution - replacing the
# picture included (same structure, better drawing). That token, not the image, is what
# :mod:`spectre.core.versioning` compares, since two pictures say nothing about what changed.
IMAGE_REVISION_KEY = "structure_image_revision"

# What a drawn structure leaves in Experiment.metadata that no longer describes an image-mode
# experience evolved from it (the StructureForge process, a campaign's split) - dropped when
# continuing with an image, the same way the builder's evolution drops IMAGE_REVISION_KEY.
DRAWN_STRUCTURE_METADATA_KEYS = (
    "structureforge_process",
    "campaign_labels",
    "campaign_factor_labels",
    "campaign_factor_values",
    "campaign_factor_scales",
    "campaign_plan",
)


def is_image_structure(structure_type: str) -> bool:
    return structure_type == StructureImage.registry_key()


def structure_images(structure_type: str, structure_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The pictures of an image-mode experience as plain dicts, in reading order (whatever shape
    they were stored in) - ``None`` for a drawn structure."""
    if not is_image_structure(structure_type):
        return None
    return [item.model_dump() for item in StructureImage.model_validate(structure_data).images]


def describe_image_changes(
    before_type: str, before_data: dict[str, Any], after_type: str, after_data: dict[str, Any]
) -> list[str] | None:
    """What changed between two structures when at least one of them is given as pictures, in
    plain French - Follow's own diff compares lists position by position, so a reordering or one
    added picture would read as "everything changed". ``None`` when neither side is pictures (the
    generic diff applies then)."""
    before = structure_images(before_type, before_data)
    after = structure_images(after_type, after_data)
    if before is None and after is None:
        return None
    if before is None:
        return ["Structure donnée en images (la version précédente était dessinée dans le constructeur)"]
    if after is None:
        return ["Structure redessinée dans le constructeur (la version précédente était donnée en images)"]

    kind_label = {"schema": "Schéma", "coupe": "Coupe TEM / MEB", "autre": "Autre"}
    before_ids = [img["image_id"] for img in before]
    after_ids = [img["image_id"] for img in after]
    lines: list[str] = []
    # la même place, une autre image : un remplacement plutôt qu'un ajout + un retrait
    replaced = {
        i for i, image_id in enumerate(after_ids)
        if image_id not in before_ids and i < len(before_ids) and before_ids[i] not in after_ids
    }
    lines += [f"Image {i + 1} remplacée" for i in sorted(replaced)]
    added = [i for i, image_id in enumerate(after_ids) if image_id not in before_ids and i not in replaced]
    removed = [i for i, image_id in enumerate(before_ids) if image_id not in after_ids and i not in replaced]
    if added:
        lines.append(f"{len(added)} image{'s' if len(added) > 1 else ''} ajoutée{'s' if len(added) > 1 else ''}")
    if removed:
        lines.append(f"{len(removed)} image{'s' if len(removed) > 1 else ''} retirée{'s' if len(removed) > 1 else ''}")
    kept = [image_id for image_id in after_ids if image_id in before_ids]
    if kept != [image_id for image_id in before_ids if image_id in after_ids]:
        lines.append("Ordre des images modifié")
    previous = {img["image_id"]: img for img in before}
    for i, img in enumerate(after):
        old = previous.get(img["image_id"])
        if old is None:
            continue
        if old["kind"] != img["kind"]:
            lines.append(f"Image {i + 1} : {kind_label[old['kind']]} → {kind_label[img['kind']]}")
        if old["caption"] != img["caption"]:
            lines.append(f"Image {i + 1} : légende {'modifiée' if img['caption'] else 'retirée'}")
    return lines


def new_image_revision() -> str:
    return secrets.token_hex(6)


class SubstrateSpec(BaseModel):
    material: str
    domain_width: Length
    thickness: Length


class SimulationFailedError(Exception):
    pass


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
    slug: str,
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared_params: dict[int, list[DeclaredParam]] | None = None,
) -> tuple[Geometry, list[Frame], MaterialLibrary]:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) for a caller that needs them for
    more than just a preview (e.g. to commit the result as a Follow experiment). ``slug`` is kept
    in the signature even though every microproject shares the same material/step/recipe physics now -
    callers already pass it, and a microproject-specific material library is a plausible future need.

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


_PATH_TAG_RE = re.compile(r"<path ")


def _tag_layer_indices(svg: str) -> str:
    """Insert ``data-layer-index="{k}"`` into the k-th ``<path `` tag of ``svg`` (0-based, in
    order of appearance) - ``frame_to_svg`` (external, unmodifiable) draws exactly one path per
    layer with a non-empty ``rings()``, in ``frame.layers`` order, so index ``k`` here lines up
    with ``frames_payload``'s own ``"layers"`` list (same filter, same order).
    """
    counter = itertools.count()
    return _PATH_TAG_RE.sub(lambda _m: f'<path data-layer-index="{next(counter)}" ', svg)


def frames_payload(frames: list[Frame], materials: MaterialLibrary) -> dict[str, Any]:
    material_colors = {m.name: m.color for m in materials}
    return {
        "frames": [
            {
                "step_index": frame.step_index,
                "step_kind": frame.step_kind,
                "step_name": frame.step_name,
                "svg": _tag_layer_indices(frame_to_svg(frame, material_colors)),
                # only the materials this particular frame actually shows - material_colors below
                # is the whole library (40+ entries), which would make a poor legend on its own.
                "materials": sorted({layer.material for layer in frame.layers}),
                # same order/filter as the SVG's paths (see _tag_layer_indices) - index k here is
                # the layer behind the k-th <path data-layer-index="k">.
                "layers": [
                    {
                        "material": layer.material,
                        "provenance": layer.provenance.model_dump(mode="json") if layer.provenance else None,
                    }
                    for layer in frame.layers
                    if layer.rings()
                ],
            }
            for frame in frames
        ],
        "material_colors": material_colors,
    }


CAMPAIGN_FIELD_LABELS = {
    "thickness": "Épaisseur",
    "depth": "Profondeur",
    "target_level": "Niveau cible",
    "domain_width": "Largeur du domaine",
    "material": "Matériau",
    "material_c": "Matériau plan C",
    "material_m": "Matériau plan M",
    "material_sp": "Matériau semipolaire",
    "resist_material": "Résine",
    "stop_material": "Matériau d'arrêt",
    "recipe": "Recette",
    "orientation": "Orientation",
    "rate_c": "Vitesse plan C",
    "rate_m": "Vitesse plan M",
    "rate_sp": "Vitesse semipolaire",
    "semi_polar_angle_deg": "Angle semipolaire",
    "angle_deg": "Angle",
    "openings.pitch": "Pas du réseau",
    "openings.diameter": "Diamètre d'ouverture",
}

SUBSTRATE_STEP_INDEX = -1  # un facteur à cet index fait varier le substrat plutôt qu'une étape
DECLARED_FIELD_PREFIX = "declared:"  # "declared:dopage" : un paramètre déclaré (DeclaredParam) de l'étape
FRACTION_FIELD_SUFFIX = ".fraction"  # "material.fraction" : le taux d'In/Al (%) d'un nitrure à composition


class VariantFactor(BaseModel):
    """One parameter to vary, at the step ``step_index`` (or the substrate, at
    :data:`SUBSTRATE_STEP_INDEX`), across ``values``. ``field`` names *any* parameter of that step:

    - one of its own fields - a ``Length`` (``thickness``, ``depth``...: values in that field's own
      unit), a plain number (``rate_m``, ``angle_deg``...), or a name/choice (``material``,
      ``recipe``, ``orientation``...: values are strings);
    - ``"<material field>.fraction"`` - the indium/aluminium rate (%) of a graded nitride
      (``In0.20Ga0.80N``...);
    - ``"openings.pitch"`` / ``"openings.diameter"`` - a lithography's periodic array (nm),
      regenerated around the same centre;
    - ``"declared:<name>"`` - a :class:`DeclaredParam` of the step (a doping level, say), which
      doesn't change the simulated geometry but is recorded per variant.

    ``scale`` only records how the values were laid out (``"log"`` = geometric spacing, e.g. a
    doping sweep over decades) so they can be shown back the same way; ``label`` overrides the
    factor's generated human label.
    """

    step_index: int
    field: str
    values: list[float | str]
    scale: str = "linear"  # "linear" | "log" | "list"
    label: str | None = None


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
    factor_values: list[list[float | str]]  # per entity, the raw value of each factor, same order


def format_number(value: float) -> str:
    """A factor value as people write it: ``20`` (not ``20.0``), and scientific notation for very
    large/small magnitudes - ``1e17``, ``3.16e17`` (a doping level), never
    ``100000000000000000``."""
    if value == 0:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-3:
        mantissa, exponent = f"{value:.2e}".split("e")  # 3 chiffres significatifs : "3.16e+17"
        return f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6g}"


def _format_value_label(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return format_number(float(value))
    return str(value)


def _numeric(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SimulationFailedError(f"{field!r} attend des valeurs numériques (reçu {value!r})") from exc


def _variable_fields(step: ProcessStep) -> list[str]:
    return [
        name
        for name in type(step).model_fields
        if name not in ("kind", "name", "description") and isinstance(getattr(step, name, None), (Length, int, float, str, Enum))
    ]


def _openings_with(openings: list[tuple[float, float]], domain_nm: float, *, pitch: float | None = None, diameter: float | None = None) -> list[tuple[float, float]]:
    """Regenerate a lithography's periodic openings with a new pitch or diameter (nm), keeping
    their count and the centre of the array - the same "pitch + diameter" generator the builder
    offers (``generatePeriodicOpenings`` in form-widgets.js), applied to an existing array."""
    ordered = sorted(openings)
    if not ordered:
        raise SimulationFailedError("cette lithographie n'a aucune ouverture à faire varier")
    # une ouverture coupée par un bord du domaine est plus étroite que les autres : son vrai centre
    # se déduit du bord resté intact, avec la largeur des ouvertures entières
    full = max(b - a for a, b in ordered)
    centers = []
    for a, b in ordered:
        if b - a < full - 1e-6 and a <= 1e-6:
            centers.append(b - full / 2)
        elif b - a < full - 1e-6 and b >= domain_nm - 1e-6:
            centers.append(a + full / 2)
        else:
            centers.append((a + b) / 2)
    width = diameter if diameter is not None else full
    if width <= 0:
        raise SimulationFailedError("le diamètre d'ouverture doit être positif")
    if pitch is not None:
        if len(ordered) < 2:
            raise SimulationFailedError("il faut au moins deux ouvertures pour faire varier le pas du réseau")
        middle = (centers[0] + centers[-1]) / 2
        centers = [middle + (i - (len(ordered) - 1) / 2) * pitch for i in range(len(ordered))]
    spacing = min((b - a for a, b in zip(centers, centers[1:])), default=None)
    if spacing is not None and width >= spacing:
        raise SimulationFailedError(f"ouvertures de {format_number(width)} nm plus larges que le pas ({format_number(spacing)} nm) : elles se chevaucheraient")
    result = []
    for center in centers:
        a, b = max(0.0, center - width / 2), min(domain_nm, center + width / 2)
        if b > a:
            result.append((round(a, 3), round(b, 3)))
    if not result:
        raise SimulationFailedError("aucune ouverture ne tombe dans le domaine simulé")
    return result


def _step_with_value(step: ProcessStep, field: str, value: Any, domain_nm: float) -> ProcessStep:
    """``step`` with the parameter ``field`` (see :class:`VariantFactor`) set to ``value`` -
    rebuilt through the step's own model so a bad value (a name where a number is expected, an
    unknown orientation...) is refused here, before any simulation, rather than half-applied."""
    data = step.model_dump()
    if field in ("openings.pitch", "openings.diameter"):
        if not isinstance(getattr(step, "openings", None), list):
            raise SimulationFailedError(f"{field!r} ne s'applique qu'à une lithographie")
        number = _numeric(value, field)
        key = "pitch" if field == "openings.pitch" else "diameter"
        data["openings"] = _openings_with(step.openings, domain_nm, **{key: number})
    elif field.endswith(FRACTION_FIELD_SUFFIX):
        base = field[: -len(FRACTION_FIELD_SUFFIX)]
        match = _GRADED_NITRIDE_RE.match(str(getattr(step, base, "") or ""))
        if not match:
            raise SimulationFailedError(f"{base!r} n'est pas un nitrure à composition (InGaN/AlGaN à un taux donné) sur cette étape")
        fraction = min(1.0, max(0.0, round(_numeric(value, field) / 100, 2)))
        data[base] = (indium_gan if match.group(1) == "In" else aluminum_gan)(fraction).name
    else:
        if field not in type(step).model_fields or field in ("kind", "name", "description"):
            raise SimulationFailedError(
                f"{field!r} n'est pas un paramètre modifiable de cette étape (paramètres disponibles : {_variable_fields(step)!r})"
            )
        current = getattr(step, field)
        if isinstance(current, Length):
            data[field] = Length(value=_numeric(value, field), unit=current.unit)
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            data[field] = _numeric(value, field)
        else:
            data[field] = value
    try:
        return type(step).model_validate(data)
    except ValidationError as exc:
        raise SimulationFailedError(f"valeur {value!r} invalide pour {field!r} : {exc.errors()[0].get('msg', exc)}") from exc


def _substrate_with_value(substrate: SubstrateSpec, field: str, value: Any) -> SubstrateSpec:
    if field in ("thickness", "domain_width"):
        current: Length = getattr(substrate, field)
        return substrate.model_copy(update={field: Length(value=_numeric(value, field), unit=current.unit)})
    if field == "material":
        if not isinstance(value, str):
            raise SimulationFailedError(f"'material' attend un nom de matériau (reçu {value!r})")
        return substrate.model_copy(update={"material": value})
    raise SimulationFailedError(f"{field!r} n'est pas un paramètre du substrat (thickness, domain_width, material)")


def _declared_with_value(declared: dict[int, list[DeclaredParam]], step_index: int, name: str, value: Any) -> dict[int, list[DeclaredParam]]:
    params = list(declared.get(step_index, []))
    existing = next((i for i, p in enumerate(params) if p.name == name), None)
    if existing is None:
        params.append(DeclaredParam(name=name, value=value))
    else:
        params[existing] = params[existing].model_copy(update={"value": value})
    return {**declared, step_index: params}


def _factor_label(factor: VariantFactor, steps: list[ProcessStep]) -> str:
    if factor.label:
        return factor.label
    target = "Substrat" if factor.step_index == SUBSTRATE_STEP_INDEX else steps[factor.step_index].name
    if factor.field.startswith(DECLARED_FIELD_PREFIX):
        field_label = factor.field[len(DECLARED_FIELD_PREFIX) :]
    elif factor.field.endswith(FRACTION_FIELD_SUFFIX):
        field_label = "Taux (%)"
    else:
        field_label = CAMPAIGN_FIELD_LABELS.get(factor.field, factor.field)
    return f"{field_label} — {target}"


def generate_campaign_variants(
    slug: str,
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    plan: VariantPlan,
    declared_params: dict[int, list[DeclaredParam]] | None = None,
) -> CampaignVariants:
    """Re-simulate ``steps`` once per combination in the full cross of every factor's values,
    varying each factor's parameter for that combination - everything else (substrate, every
    other step, every other field) held constant. Returns one flattened ``ProcessStructure``
    and one preview SVG per combination, plus Follow's own constant/varying split
    (``follow.doe.batch.analyze_batch``) so the "matrice de split" is available before anyone
    commits to the campaign, not only after. A factor on a declared parameter leaves the geometry
    untouched - its value per variant lives in ``factor_values``, like every other factor's.
    """
    if not plan.factors:
        raise SimulationFailedError("il faut au moins un paramètre à faire varier")
    for factor in plan.factors:
        if not factor.values:
            raise SimulationFailedError("il faut au moins une valeur pour chaque paramètre")
        if not (SUBSTRATE_STEP_INDEX <= factor.step_index < len(steps)):
            raise SimulationFailedError("étape sélectionnée invalide")
        if not factor.field:
            raise SimulationFailedError("il faut choisir un paramètre à faire varier")
        if factor.step_index == SUBSTRATE_STEP_INDEX and factor.field.startswith(DECLARED_FIELD_PREFIX):
            raise SimulationFailedError("le substrat n'a pas de paramètres déclarés")

    factor_labels = [_factor_label(factor, steps) for factor in plan.factors]
    base_declared = declared_params or {}

    entries: list[ProcessStructure] = []
    svgs: list[str] = []
    labels: list[str] = []
    factor_values: list[list[float | str]] = []
    for combo in itertools.product(*(factor.values for factor in plan.factors)):
        varied_substrate = substrate
        varied_steps = list(steps)
        varied_declared = base_declared
        for factor, value in zip(plan.factors, combo):
            if factor.step_index == SUBSTRATE_STEP_INDEX:
                varied_substrate = _substrate_with_value(varied_substrate, factor.field, value)
            elif factor.field.startswith(DECLARED_FIELD_PREFIX):
                varied_declared = _declared_with_value(varied_declared, factor.step_index, factor.field[len(DECLARED_FIELD_PREFIX) :], value)
            else:
                domain_nm = varied_substrate.domain_width.to_nm()
                varied_steps[factor.step_index] = _step_with_value(varied_steps[factor.step_index], factor.field, value, domain_nm)
        geometry, frames, materials = run_simulation(slug, varied_substrate, varied_steps, varied_declared or None)
        entries.append(to_structure(geometry))
        material_colors = {m.name: m.color for m in materials}
        svgs.append(frame_to_svg(frames[-1], material_colors))
        labels.append(" · ".join(_format_value_label(v) for v in combo))
        factor_values.append(list(combo))

    variation = analyze_variants(entries)
    return CampaignVariants(
        entries=entries, svgs=svgs, variation=variation, labels=labels, factor_labels=factor_labels, factor_values=factor_values
    )


def _layer_extents(entry: ProcessStructure) -> dict[str, Any]:
    """A variant reduced to what can always be compared: each layer's material and bounding box."""
    layers = []
    for layer in entry.layers:
        points = [point for ring in layer.rings for point in ring.get("exterior", [])]
        xs = [p[0] for p in points] or [0.0]
        ys = [p[1] for p in points] or [0.0]
        layers.append(
            {
                "material": layer.material,
                "x_min": round(min(xs), 3),
                "x_max": round(max(xs), 3),
                "y_min": round(min(ys), 3),
                "y_max": round(max(ys), 3),
            }
        )
    return {"domain_width_nm": entry.domain_width_nm, "layers": layers}


def analyze_variants(entries: list[ProcessStructure]) -> BatchVariation:
    """Follow's constant/varying split (``follow.doe.batch.analyze_batch``) of a campaign's
    variants - which compares them point by point, so it refuses variants whose outlines don't
    have the same number of points (a facet growth rate, a material or a pitch that changes the
    polygons). Then each layer is compared by its extent instead (material + bounding box), and if
    even the layer count differs, only the entity count is reported: the factors the campaign was
    launched with (``campaign_factor_labels``/``values``) still say exactly what varies.
    """
    try:
        return analyze_batch(entries)
    except BatchShapeError:
        pass
    try:
        return analyze_batch([_layer_extents(entry) for entry in entries])
    except BatchShapeError:
        return BatchVariation(entity_count=len(entries))


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


def declared_params_by_index(raw: dict[str, list[DeclaredParam]] | None) -> dict[int, list[DeclaredParam]]:
    """A request's ``declared_params`` (JSON object keys are always strings) keyed by step index,
    empty lists dropped."""
    return {int(k): v for k, v in (raw or {}).items() if v}


def declared_params_json(declared_params: dict[int, list[DeclaredParam]] | None) -> dict[str, list[dict[str, Any]]]:
    return {str(i): [p.model_dump(mode="json") for p in params] for i, params in sorted((declared_params or {}).items()) if params}


def process_metadata(
    substrate: SubstrateSpec, steps: list[ProcessStep], declared_params: dict[int, list[DeclaredParam]] | None = None
) -> dict[str, Any]:
    """The raw, re-editable process (substrate + typed steps) as plain JSON - stashed on the
    committed ``Experiment.metadata`` under this key, since the ``Structure`` Follow stores is the
    *flattened* result (see ``structureforge.adapters.follow_adapter.ProcessStructure``) and can't
    be turned back into an editable step list on its own. See :mod:`spectre.api.structures` for
    where this is read back to pre-fill the builder when evolving an experiment.

    The steps' declared parameters (:class:`DeclaredParam` - never part of a ``ProcessStep``) ride
    along under ``"declared_params"``, keyed by step index - only when there are some, so a
    process without any keeps exactly its former shape (and :mod:`spectre.core.versioning` sees no
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
