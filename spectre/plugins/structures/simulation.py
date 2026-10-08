"""Bridges the structure-builder page to StructureForge: which materials and recipes a structure can
draw on, and turning a substrate + step list into simulated frames the page can show. All the
physics stays in ``structureforge`` - a ``Deposition``/``Etch`` step names a recipe from the
recipe library by string key (mode/angle/selectivity live on the recipe, not the step), resolved
here at simulation time - the library's recipes, plus the process's own
(:class:`ProcessRecipes`: a selective etch defined right in the builder). Turning each ``Frame`` into ready-to-embed SVG is
:mod:`spectre.plugins.structures.rendering`'s, through ``structureforge.presentation.svg.frame_to_svg``,
so Spectre never draws a cross-section itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import threading
from collections import OrderedDict
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
from structureforge.core.recipes import DepositionRecipe, EtchRecipe, RecipeLibrary, default_recipes
from structureforge.core.traced import Traced
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry, Layer, LayerProvenance
from structureforge.process.simulate import Frame, SimulationError, simulate
from structureforge.process.steps import Flip, ProcessStep

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
    # l'unité de la valeur (« cm⁻³ », « % », « °C »...), écrite sur l'étiquette de la couche ; venue
    # après les paramètres eux-mêmes : un paramètre sans unité s'enregistre sans la clé (la forme
    # d'avant, que le versionnage compare)
    unit: str | None = Field(None, max_length=20)

    @field_validator("unit")
    @classmethod
    def _strip_unit(cls, unit: str | None) -> str | None:
        return (unit or "").strip() or None

    @model_serializer(mode="wrap")
    def _without_empty_unit(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if not data.get("unit"):
            data.pop("unit", None)
        return data

    def unit_text(self) -> str:
        """L'unité de la valeur : son champ ``unit``, ou, pour un paramètre enregistré avant lui,
        l'astuce d'alors - une clé ``unit`` (``unité``, ``unite``) de l'obtention."""
        return self.unit or declared_unit_in_obtention(self.obtention)


# les clés d'obtention où l'on écrivait l'unité avant le champ ``unit`` (toujours lues)
OBTENTION_UNIT_KEYS = ("unit", "unité", "unite")


def declared_unit_in_obtention(obtention: dict[str, Any] | None) -> str:
    return next((str(obtention[key]) for key in OBTENTION_UNIT_KEYS if (obtention or {}).get(key)), "")


def split_declared_unit(param: Any) -> tuple[Any, str]:
    """Un paramètre déclaré (en JSON) sans son unité, et son unité : son champ ``unit``, ou la clé
    ``unit`` (``unité``, ``unite``) de son obtention, l'astuce d'avant le champ."""
    if not isinstance(param, dict):
        return param, ""
    obtention = param.get("obtention") if isinstance(param.get("obtention"), dict) else {}
    unit = param.get("unit") or next((obtention[key] for key in OBTENTION_UNIT_KEYS if obtention.get(key)), "")
    rest = {key: value for key, value in param.items() if key not in ("unit", "obtention")}
    rest["obtention"] = {key: value for key, value in obtention.items() if key not in OBTENTION_UNIT_KEYS}
    return rest, str(unit or "")


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

    base = default_library()
    if "AlGaN" in base:  # l'AlGaN générique, au même rose que les compositions
        base = base.with_materials(base.get("AlGaN").model_copy(update={"color": aluminum_gan_color(0.3)}))
    library = base.with_materials(*materials())
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
    if material.name != name:
        return None
    if symbol == "Al":
        material = material.model_copy(update={"color": aluminum_gan_color(float(fraction_str))})
    return material


# AlGaN en rose/magenta : StructureForge le fond entre le violet-gris du GaN et le violet pâle de
# l'AlN, impossible à distinguer du GaN à 10-20 % d'Al. Le magenta est la seule teinte que ni le
# GaN ni l'arc-en-ciel de l'InGaN (violet → rouge) n'utilisent ; plus d'Al = plus pâle.
_ALGAN_LOW_AL = (0xD0, 0x1C, 0x8B)  # peu d'aluminium : magenta franc
_ALGAN_HIGH_AL = (0xF6, 0xC8, 0xE0)  # beaucoup d'aluminium : rose pâle


def aluminum_gan_color(fraction: float) -> str:
    t = min(max(fraction, 0.0), 1.0)
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(_ALGAN_LOW_AL, _ALGAN_HIGH_AL))


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


MAX_PROCESS_RECIPES = 50  # par type (dépôt, gravure)


class ProcessRecipes(BaseModel):
    """The process's own recipes: a deposition or an etch defined right in the builder (a selective
    etch of one material, its mode, angle and selectivity table) rather than in the root library's
    ``recettes.yml``. A step names one like any other recipe; one of them wins over a library
    recipe of the same name. They travel with the process (a request's ``recipes``, a study's
    ``structureforge_process``, a saved structure, a brick, a step preset) - so an edit of the
    library never changes a process that defined its own."""

    model_config = ConfigDict(extra="forbid")

    deposition: list[DepositionRecipe] = Field(default_factory=list, max_length=MAX_PROCESS_RECIPES)
    etch: list[EtchRecipe] = Field(default_factory=list, max_length=MAX_PROCESS_RECIPES)

    @model_validator(mode="after")
    def _named_once(self) -> "ProcessRecipes":
        for kind, recipes in (("dépôt", self.deposition), ("gravure", self.etch)):
            names = [recipe.name.strip() for recipe in recipes]
            if any(not name or len(name) > 120 for name in names):
                raise ValueError(f"une recette de {kind} du procédé a un nom (120 caractères au plus)")
            if len(set(names)) != len(names):
                raise ValueError(f"deux recettes de {kind} du procédé portent le même nom")
        return self

    def __bool__(self) -> bool:
        return bool(self.deposition or self.etch)

    def as_json(self) -> dict[str, Any]:
        """As a process records them: only the kinds that have some."""
        data = self.model_dump(mode="json")
        return {kind: recipes for kind, recipes in data.items() if recipes}


def process_recipes(raw: Any) -> ProcessRecipes | None:
    """The recipes a recorded process carries (its ``"recipes"``), ``None`` without any."""
    recipes = ProcessRecipes.model_validate(raw) if isinstance(raw, dict) else None
    return recipes or None


def recipes_library(own: ProcessRecipes | None = None) -> RecipeLibrary:
    """StructureForge's default recipes plus any extra ones from the editable root library
    (``library/recettes.yml`` via :func:`spectre.plugins.structures.library_files.recipes`), plus
    the process's ``own`` (:class:`ProcessRecipes`), which win over a library recipe of the same name.
    """
    from .library_files import recipes

    deposition, etch = recipes()
    base = default_recipes()
    library = base.with_recipes(deposition=deposition, etch=etch) if (deposition or etch) else base
    return library.with_recipes(deposition=own.deposition, etch=own.etch) if own else library


class PresetOrigin(BaseModel):
    """The step preset a step was inserted from (``process_library``'s ``StepPreset``): its id, its
    name and its version then - a trace, never a live link: the step keeps its own fields, and a
    later edit of the preset changes nothing here. Travels with the process, by step index, like
    the declared parameters (``preset_origins``)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    version: int = Field(1, ge=1)


def preset_origins_by_index(raw: dict[str, PresetOrigin] | None, step_count: int) -> dict[int, PresetOrigin]:
    """A request's ``preset_origins`` by step position - one outside the process is dropped."""
    origins: dict[int, PresetOrigin] = {}
    for key, origin in (raw or {}).items():
        index = int(key) if key.isascii() and key.isdigit() else -1
        if 0 <= index < step_count:
            origins[index] = origin
    return origins


def preset_origins_json(origins: dict[int, PresetOrigin] | None) -> dict[str, dict[str, Any]]:
    return {str(i): origin.model_dump(mode="json") for i, origin in sorted((origins or {}).items())}


SUBSTRATE_ORIGIN = -1  # l'« étape » d'une couche du substrat de départ


class SimulationResult(NamedTuple):
    """Une simulation et la provenance de ses couches : ``layer_origins[k][j]`` est la position
    (à partir de 0) de l'étape qui a créé la ``j``-ième couche de ``frames[k]`` (dans l'ordre de
    ``frame.layers``), :data:`SUBSTRATE_ORIGIN` pour le substrat."""

    geometry: Geometry
    frames: list[Frame]
    materials: MaterialLibrary
    layer_origins: list[list[int]]


# -- la reprise d'une simulation -------------------------------------------------------------------
#
# Le constructeur resimule tout le procédé à chaque retouche (une frappe dans un champ, une étiquette
# déplacée, une brique), alors qu'une étape ne dépend que de celles d'avant. Chaque état atteint est
# donc gardé, en mémoire du serveur (les :data:`MAX_CHECKPOINTS` derniers servis), sous une clé qui
# résume tout ce qui l'a produit : le substrat, les bibliothèques (matériaux racine, recettes) et
# les étapes jusque-là. Une simulation repart du plus long début déjà calculé : une étiquette ou un
# paramètre déclaré ne relance rien, une retouche de l'étape k ne recalcule qu'elle et la suite, et
# les variantes d'une campagne partagent les étapes d'avant leurs facteurs. Mêmes images qu'une
# simulation complète : StructureForge ne garde rien d'autre que les couches et le plancher.

MAX_CHECKPOINTS = 512


class _Checkpoint(NamedTuple):
    """L'état après une étape (ou le substrat seul) : les couches de la géométrie (matériau, contour,
    provenance, position de l'étape qui l'a créée), son plancher, et l'image de l'étape avec l'origine
    de ses couches. Jamais rendu tel quel : une reprise recrée ses propres couches et images, qu'une
    étape suivante ou les paramètres déclarés modifient."""

    layers: tuple[tuple[str, Any, LayerProvenance | None, int], ...]
    floor_nm: float | None
    frame: Frame
    frame_origins: tuple[int, ...]


_checkpoints: OrderedDict[str, _Checkpoint] = OrderedDict()
_checkpoints_lock = threading.Lock()


def _checkpoint_keys(substrate: SubstrateSpec, steps: list[ProcessStep], recipes: RecipeLibrary) -> list[str]:
    """La clé de l'état de départ, puis de l'état après chaque étape : chacune résume la précédente
    et l'étape, si bien que deux procédés partagent les clés de leur début commun."""
    from .library_files import materials

    context = {
        "substrate": substrate.model_dump(mode="json"),
        # le matériau d'une couche décide de sa vitesse de gravure (sa catégorie)
        "materials": [material.model_dump(mode="json") for material in materials()],
        "recipes": recipes.model_dump(mode="json"),
    }
    key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    keys = [key]
    for step in steps:
        key = hashlib.sha256((key + json.dumps(step.model_dump(mode="json"), sort_keys=True)).encode()).hexdigest()
        keys.append(key)
    return keys


def _copied_frame(frame: Frame) -> Frame:
    return Frame(frame.step_index, frame.step_kind, frame.step_name, [Layer(l.material, l.polygon, l.provenance) for l in frame.layers], frame.domain_width_nm)


def _cached_start(keys: list[str]) -> list[_Checkpoint]:
    """Les états gardés du plus long début de ``keys`` (vide : rien de gardé, pas même le départ)."""
    reached: list[_Checkpoint] = []
    with _checkpoints_lock:
        for key in keys:
            checkpoint = _checkpoints.get(key)
            if checkpoint is None:
                break
            _checkpoints.move_to_end(key)
            reached.append(checkpoint)
    return reached


def _keep(key: str, geometry: Geometry, origin: dict[int, int], frame: Frame, frame_origins: list[int]) -> None:
    checkpoint = _Checkpoint(
        tuple((layer.material, layer.polygon, layer.provenance, origin[id(layer)]) for layer in geometry.layers),
        geometry.floor_nm,
        _copied_frame(frame),
        tuple(frame_origins),
    )
    with _checkpoints_lock:
        _checkpoints[key] = checkpoint
        _checkpoints.move_to_end(key)
        while len(_checkpoints) > MAX_CHECKPOINTS:
            _checkpoints.popitem(last=False)


def _simulate_tracking(
    substrate: SubstrateSpec, steps: list[ProcessStep], materials: MaterialLibrary, recipes: RecipeLibrary
) -> tuple[Geometry, list[Frame], list[list[int]]]:
    """``structureforge.process.simulate.simulate``, une étape à la fois - mêmes images, mêmes
    erreurs - pour savoir quelle étape a créé chaque couche. StructureForge ne le dit que pour une
    croissance (``LayerProvenance``, sans la position de l'étape) : on suit donc les couches de la
    géométrie elles-mêmes, entre deux étapes. Une couche y garde son objet tant qu'elle existe (une
    gravure change son contour, pas l'objet) ; une étape ajoute les siennes à la fin ; un
    retournement (``Flip``) recrée toutes les couches, dans l'ordre inverse. Repart du plus long
    début déjà simulé (voir plus haut), et garde chaque état atteint."""
    keys = _checkpoint_keys(substrate, steps, recipes)
    reached = _cached_start(keys)
    width = substrate.domain_width.to_nm()
    if reached:
        last = reached[-1]
        geometry = Geometry(width, [Layer(material, polygon, provenance) for material, polygon, provenance, _o in last.layers])
        geometry.floor_nm = last.floor_nm
        origin = {id(layer): kept[3] for layer, kept in zip(geometry.layers, last.layers)}
        frames = [_copied_frame(checkpoint.frame) for checkpoint in reached]
        origins = [list(checkpoint.frame_origins) for checkpoint in reached]
    else:
        geometry = Geometry.substrate(substrate.material, width, substrate.thickness.to_nm())
        frames = simulate(geometry, [], materials, recipes)
        origin = {id(layer): SUBSTRATE_ORIGIN for layer in geometry.layers}
        origins = [[origin[id(layer)] for layer in geometry.frame_layers()]]
        _keep(keys[0], geometry, origin, frames[0], origins[0])
    alive: list[Any] = list(geometry.layers)  # garde chaque couche vivante : son id() n'est jamais redonné
    for index in range(len(frames) - 1, len(steps)):
        step = steps[index]
        before = list(geometry.layers)
        try:
            frame = simulate(geometry, [step], materials, recipes)[-1]
        except SimulationError as exc:
            raise SimulationError(index + 1, step, exc.original) from exc.original
        if isinstance(step, Flip):
            # les couches retournées, dans l'ordre inverse (moins celles devenues vides)
            survivors = [layer for layer in reversed(before) if not layer.polygon.is_empty]
            if len(survivors) == len(geometry.layers):
                for old, new in zip(survivors, geometry.layers):
                    origin.setdefault(id(new), origin.get(id(old), index))
        for layer in geometry.layers:
            origin.setdefault(id(layer), index)
        alive.extend(geometry.layers)
        frames.append(Frame(index + 1, frame.step_kind, frame.step_name, frame.layers, frame.domain_width_nm))
        origins.append([origin[id(layer)] for layer in geometry.frame_layers()])
        _keep(keys[index + 1], geometry, origin, frames[-1], origins[-1])
    return geometry, frames, origins


def _apply_declared_params(
    frames: list[Frame], origins: list[list[int]], declared_params: dict[int, list[DeclaredParam]], steps: list[ProcessStep]
) -> None:
    """Merge user-declared parameters (see :class:`DeclaredParam`) onto every layer each step
    created, in every frame where it shows - the provenance of the layers (``origins``, see
    :class:`SimulationResult`) says which step that is. A step that created no layer (etch,
    planarization, flip, chemical...) has nowhere to put them."""
    for frame, frame_origins in zip(frames, origins):
        for layer, step_index in zip(frame.layers, frame_origins):
            params = declared_params.get(step_index)
            if not params:
                continue
            provenance = layer.provenance
            parameters = dict(provenance.parameters) if provenance is not None else {}
            for param in params:
                obtention = {**param.obtention, "unit": param.unit} if param.unit else param.obtention
                parameters[param.name] = Traced.declared(param.value, **obtention)
            step = steps[step_index]
            layer.provenance = LayerProvenance(
                step_kind=provenance.step_kind if provenance is not None else step.kind,
                step_name=provenance.step_name if provenance is not None else step.name,
                parameters=parameters,
            )


def simulate_process(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared_params: dict[int, list[DeclaredParam]] | None = None,
    recipes: ProcessRecipes | None = None,
) -> SimulationResult:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) and which step created each layer of
    each frame, for a caller that needs them for more than just a preview (e.g. to commit the
    result as a Follow experiment). Every microproject shares the same material/step/recipe physics.

    ``declared_params`` (step_index -> extra parameters the user attached in the builder, see
    :class:`DeclaredParam`) is Spectre-only bookkeeping never seen by ``structureforge`` itself -
    it's merged onto the resulting layers' ``provenance`` after simulation succeeds. ``recipes``:
    the process's own (:class:`ProcessRecipes`), on top of the library's.
    """
    steps = _expand_seed_material_aliases(steps, substrate.material)
    materials = materials_library(substrate.material, *_material_names_in_steps(steps))
    recipe_library = recipes_library(recipes)
    try:
        materials.get(substrate.material)
    except KeyError as exc:
        raise SimulationFailedError(str(exc)) from exc

    try:
        geometry, frames, origins = _simulate_tracking(substrate, steps, materials, recipe_library)
    except SimulationError as exc:
        raise SimulationFailedError(str(exc)) from exc
    if declared_params:
        _apply_declared_params(frames, origins, declared_params, steps)
    return SimulationResult(geometry, frames, materials, origins)


def run_simulation(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared_params: dict[int, list[DeclaredParam]] | None = None,
) -> tuple[Geometry, list[Frame], MaterialLibrary]:
    """:func:`simulate_process` without the provenance of the layers: (geometry, frames, materials)."""
    result = simulate_process(substrate, steps, declared_params)
    return result.geometry, result.frames, result.materials


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
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared_params: dict[int, list[DeclaredParam]] | None = None,
    recipes: ProcessRecipes | None = None,
    preset_origins: dict[int, PresetOrigin] | None = None,
) -> dict[str, Any]:
    """The raw, re-editable process (substrate + typed steps) as plain JSON - stashed on the
    committed ``Experiment.metadata`` under this key, since the ``Structure`` Follow stores is the
    *flattened* result (see ``structureforge.adapters.follow_adapter.ProcessStructure``) and can't
    be turned back into an editable step list on its own. See :mod:`spectre.plugins.experiments.api` for
    where this is read back to pre-fill the builder when evolving an experiment.

    The steps' declared parameters (:class:`DeclaredParam` - never part of a ``ProcessStep``) ride
    along under ``"declared_params"``, keyed by step index - only when there are some, so a
    process without any keeps exactly its former shape (and :mod:`spectre.plugins.experiments.versioning` sees no
    spurious change on lineages recorded before they were kept). The process's own recipes
    (:class:`ProcessRecipes`) ride along under ``"recipes"`` the same way, only when there are some,
    and so do the presets the steps were inserted from (:class:`PresetOrigin`, ``"preset_origins"``,
    by step index).
    """
    process: dict[str, Any] = {
        "substrate": substrate.model_dump(mode="json"),
        "steps": [step.model_dump(mode="json") for step in steps],
    }
    declared = declared_params_json(declared_params)
    if declared:
        process["declared_params"] = declared
    if recipes:
        process["recipes"] = recipes.as_json()
    origins = preset_origins_json(preset_origins)
    if origins:
        process["preset_origins"] = origins
    return process


# -- les étiquettes de couches ---------------------------------------------------------------------
#
# Une étape choisie peut porter une étiquette, dessinée à droite de la structure et reliée à la
# couche qu'elle a créée : un texte (« p-GaN » ; vide, le nom du matériau) et, dessous, des valeurs
# de l'étape (épaisseur, composition d'un nitrure, paramètres déclarés), pour qu'une capture d'écran
# porte l'essentiel. Une requête (simulation, lancement, bibliothèque) les range par position
# d'étape, comme les paramètres déclarés ; une étude, par id d'étape, sous
# :data:`LAYER_LABELS_METADATA_KEY` - à part du procédé, comme les ids (le versionnage n'en fait
# qu'un changement de niveau correctif). Avec elles, la provenance des couches de la structure
# enregistrée (:data:`LAYER_STEPS_METADATA_KEY`), qui seule relie une couche à son étape.

LAYER_LABELS_METADATA_KEY = "process_layer_labels"
# l'id de l'étape qui a créé chaque couche de la structure (None : le substrat), une liste par entité
# (une pour une étude simple, une par variante d'une campagne) - enregistrée avec les étiquettes
LAYER_STEPS_METADATA_KEY = "process_layer_steps"

LABEL_THICKNESS = "thickness"
LABEL_COMPOSITION = "composition"
LABEL_DEPTH = "depth"  # la profondeur d'une gravure, sur sa marque d'interface
LABEL_DECLARED_PREFIX = "declared:"
MAX_LABEL_TEXT = 40
MAX_LABEL_VALUES = 6
# le plus loin qu'on puisse déplacer une étiquette de sa place automatique (unités du dessin, où la
# structure tient dans un carré de 400 : spectre.plugins.structures.rendering.STRUCTURE_BOX)
MAX_LABEL_OFFSET = 2000.0
# ce qui, d'une étiquette, n'est que sa place sur le dessin (texte déplacé, point d'accroche posé à
# la main) : ni le versionnage, ni les différences d'étiquettes, ni un préset ne le comptent
LABEL_PLACE_KEYS = ("offset", "anchor")
# les étapes qui ne créent pas de couche (un nettoyage, une gravure, un etch back...) : leur étiquette
# est une marque d'interface, reliée à la surface telle qu'elle était quand l'étape a eu lieu - entre
# les couches d'avant et celles d'après (spectre.plugins.structures.rendering)
INTERFACE_STEP_KINDS = frozenset({"etch", "planarization", "chemical", "resist_strip"})


class LayerLabel(BaseModel):
    """L'étiquette d'une étape : son texte et les valeurs à écrire dessous, dans l'ordre -
    ``"thickness"``, ``"composition"`` (le taux d'In/Al d'un nitrure à composition), ``"depth"``
    (la profondeur d'une gravure) ou ``"declared:<nom>"`` (un :class:`DeclaredParam` de l'étape).
    Une valeur que l'étape n'a pas n'est simplement pas écrite. Sur une étape qui ne crée pas de
    couche (:data:`INTERFACE_STEP_KINDS`), l'étiquette est une marque d'interface.
    ``offset`` : ``(dx, dy)``, de combien le texte a été déplacé à la main depuis sa place
    automatique (unités du dessin) - ``None`` (et absent de l'enregistrement) : à sa place. Le trait
    suit le texte ; le point d'accroche sur la couche ne bouge pas.
    ``anchor`` : ``(fx, fy)``, où le point d'accroche a été posé à la main - en fractions du cadre de
    ce que l'étiquette désigne (les couches de l'étape ; pour une marque d'interface, les couches
    d'avant elle), de gauche à droite et de haut en bas : le point suit la couche quand elle change
    (une épaisseur, une variante), et ramené sur elle s'il en sort - sur la surface pour une marque
    d'interface. ``None`` (et absent de l'enregistrement) : le point automatique. L'étiquette d'une
    brique (une accolade) n'en a pas. Ni l'un ni l'autre ne change la version (:data:`LABEL_PLACE_KEYS`)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field("", max_length=MAX_LABEL_TEXT)
    values: list[str] = Field(default_factory=list, max_length=MAX_LABEL_VALUES)
    offset: tuple[float, float] | None = None
    anchor: tuple[float, float] | None = None

    @field_validator("offset")
    @classmethod
    def _bounded_offset(cls, offset: tuple[float, float] | None) -> tuple[float, float] | None:
        if offset is None:
            return None
        if not all(math.isfinite(v) and abs(v) <= MAX_LABEL_OFFSET for v in offset):
            raise ValueError(f"déplacement d'étiquette hors limites (±{MAX_LABEL_OFFSET:g})")
        dx, dy = (round(v, 1) for v in offset)
        return None if dx == 0 and dy == 0 else (dx, dy)

    @field_validator("anchor")
    @classmethod
    def _anchor_in_frame(cls, anchor: tuple[float, float] | None) -> tuple[float, float] | None:
        if anchor is None:
            return None
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in anchor):
            raise ValueError("point d'accroche hors de son cadre (deux fractions entre 0 et 1)")
        fx, fy = (round(v, 3) for v in anchor)
        return (fx, fy)

    @model_serializer(mode="wrap")
    def _without_default_place(self, handler: Any) -> dict[str, Any]:
        # une étiquette à sa place s'enregistre comme avant les déplacements : {text, values}
        data = handler(self)
        for key in LABEL_PLACE_KEYS:
            if data.get(key) is None:
                data.pop(key, None)
        return data

    @field_validator("text")
    @classmethod
    def _strip(cls, text: str) -> str:
        return text.strip()

    @field_validator("values")
    @classmethod
    def _known_values(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            declared = value.startswith(LABEL_DECLARED_PREFIX) and 0 < len(value) - len(LABEL_DECLARED_PREFIX) <= 100
            if value not in (LABEL_THICKNESS, LABEL_COMPOSITION, LABEL_DEPTH) and not declared:
                raise ValueError(f"valeur d'étiquette inconnue : {value!r} (thickness, composition, depth ou declared:<nom>)")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned


def layer_labels_by_index(raw: dict[str, LayerLabel] | None, step_count: int) -> dict[int, LayerLabel]:
    """Les étiquettes d'une requête (clés : la position de l'étape, en texte) par position - une
    position hors du procédé est refusée (422 ``invalid_layer_label``)."""
    labels: dict[int, LayerLabel] = {}
    for key, label in (raw or {}).items():
        index = int(key) if key.isascii() and key.isdigit() else -1  # "²".isdigit(), mais int("²") échoue
        if not 0 <= index < step_count:
            raise InvalidInput(f"Étiquette de couche sur une étape inconnue ({key!r}).", code="invalid_layer_label")
        labels[index] = label
    return labels


def layer_labels_json(labels: dict[int, LayerLabel] | None) -> dict[str, dict[str, Any]]:
    """Les étiquettes rangées par position d'étape, telles qu'une bibliothèque les enregistre."""
    return {str(i): label.model_dump(mode="json") for i, label in sorted((labels or {}).items())}


def label_without_place(label: Any) -> Any:
    """Une étiquette enregistrée (``{text, values, ...}``) sans sa place sur le dessin
    (:data:`LABEL_PLACE_KEYS`) : ce qui compte pour dire si elle a changé - le reste tel quel."""
    return {k: v for k, v in label.items() if k not in LABEL_PLACE_KEYS} if isinstance(label, dict) else label


# -- l'appartenance des étapes aux briques ----------------------------------------------------------
#
# Une brique technologique insérée dans le constructeur (ou formée d'étapes choisies) y reste un
# groupe d'étapes consécutives, avec son nom et la brique de bibliothèque d'où elle vient. Une
# requête (simulation, lancement, bibliothèque) range ce groupe par positions d'étape, comme les
# étiquettes ; une étude, par ids d'étape, sous :data:`BRICKS_METADATA_KEY` - à part du procédé :
# StructureForge ne la voit pas, et le versionnage n'en lit que ce qu'elle change aux étiquettes
# (un regroupement d'étiquettes, :data:`MIN_GROUPED_LABELS`).

BRICKS_METADATA_KEY = "process_bricks"
# il faut au moins deux étapes étiquetées d'une même brique pour que leurs étiquettes n'en fassent qu'une
MIN_GROUPED_LABELS = 2
BRICK_GROUP_ID_RE = r"^[A-Za-z0-9_.:-]{1,80}$"
# le nom d'une brique (celle d'un procédé comme celle de la bibliothèque, dont elle reprend le nom)
BRICK_NAME_MAX_LENGTH = 120


class ProcessBrick(BaseModel):
    """Une brique du procédé : son identifiant de groupe (celui du constructeur, gardé d'une version
    à l'autre), son nom, la brique de bibliothèque d'où elle vient (``source``, son id, si on la
    connaît) et les positions de ses étapes, consécutives."""

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(pattern=BRICK_GROUP_ID_RE)
    name: str = Field(min_length=1, max_length=BRICK_NAME_MAX_LENGTH)
    source: str | None = Field(None, max_length=120)
    step_indexes: list[int] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("une brique a un nom")
        return name

    @field_validator("source")
    @classmethod
    def _strip_source(cls, source: str | None) -> str | None:
        return (source or "").strip() or None


def checked_bricks(bricks: list[ProcessBrick] | None, step_count: int) -> list[ProcessBrick]:
    """Les briques d'une requête, vérifiées : des étapes du procédé, consécutives et dans l'ordre,
    aucune dans deux briques, deux briques jamais du même groupe - sinon 422 ``invalid_brick``."""
    seen_steps: set[int] = set()
    seen_groups: set[str] = set()
    for brick in bricks or []:
        indexes = brick.step_indexes
        if any(not 0 <= i < step_count for i in indexes):
            raise InvalidInput(f"La brique « {brick.name} » désigne une étape inconnue.", code="invalid_brick")
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            raise InvalidInput(f"Les étapes de la brique « {brick.name} » doivent se suivre.", code="invalid_brick")
        if seen_steps & set(indexes) or brick.group_id in seen_groups:
            raise InvalidInput(f"Une étape appartient à deux briques (« {brick.name} »).", code="invalid_brick")
        seen_steps.update(indexes)
        seen_groups.add(brick.group_id)
    return list(bricks or [])


def bricks_json(bricks: list[ProcessBrick] | None) -> list[dict[str, Any]]:
    return [brick.model_dump(mode="json") for brick in bricks or []]


def bricks_metadata(bricks: list[ProcessBrick], step_ids: list[str]) -> list[dict[str, Any]]:
    """Les briques telles qu'une étude les enregistre : par ids d'étape."""
    return [
        {"group_id": brick.group_id, "name": brick.name, "source": brick.source, "step_ids": [step_ids[i] for i in brick.step_indexes]}
        for brick in bricks
    ]


def bricks_from_metadata(raw: Any, step_ids: list[str]) -> list[ProcessBrick]:
    """Les briques qu'une étude a enregistrées (par ids d'étape), par positions dans ``step_ids`` -
    une étape disparue en est retirée, une brique qui n'en a plus disparaît, un enregistrement
    illisible n'en donne aucune."""
    position = {step_id: i for i, step_id in enumerate(step_ids)}
    bricks: list[ProcessBrick] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        indexes = sorted(position[sid] for sid in item.get("step_ids") or [] if isinstance(sid, str) and sid in position)
        if not indexes:
            continue
        try:
            bricks.append(ProcessBrick(group_id=item.get("group_id"), name=item.get("name"), source=item.get("source"), step_indexes=indexes))
        except (ValueError, TypeError):
            continue
    return bricks


def grouped_labels(bricks: list[ProcessBrick], labelled: set[int] | dict[int, Any]) -> list[tuple[ProcessBrick, list[int]]]:
    """Les briques dont les étiquettes n'en font qu'une : celles qui ont au moins
    :data:`MIN_GROUPED_LABELS` étapes étiquetées (``labelled``, des positions), avec ces étapes."""
    groups = []
    for brick in bricks:
        members = [i for i in brick.step_indexes if i in labelled]
        if len(members) >= MIN_GROUPED_LABELS:
            groups.append((brick, members))
    return groups
