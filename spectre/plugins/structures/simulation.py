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
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
from structureforge.core.recipes import RecipeLibrary, default_recipes
from structureforge.core.traced import Traced
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry, LayerProvenance
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


SUBSTRATE_ORIGIN = -1  # l'« étape » d'une couche du substrat de départ


class SimulationResult(NamedTuple):
    """Une simulation et la provenance de ses couches : ``layer_origins[k][j]`` est la position
    (à partir de 0) de l'étape qui a créé la ``j``-ième couche de ``frames[k]`` (dans l'ordre de
    ``frame.layers``), :data:`SUBSTRATE_ORIGIN` pour le substrat."""

    geometry: Geometry
    frames: list[Frame]
    materials: MaterialLibrary
    layer_origins: list[list[int]]


def _simulate_tracking(geometry: Geometry, steps: list[ProcessStep], materials: MaterialLibrary, recipes: RecipeLibrary) -> tuple[list[Frame], list[list[int]]]:
    """``structureforge.process.simulate.simulate``, une étape à la fois - mêmes images, mêmes
    erreurs - pour savoir quelle étape a créé chaque couche. StructureForge ne le dit que pour une
    croissance (``LayerProvenance``, sans la position de l'étape) : on suit donc les couches de la
    géométrie elles-mêmes, entre deux étapes. Une couche y garde son objet tant qu'elle existe (une
    gravure change son contour, pas l'objet) ; une étape ajoute les siennes à la fin ; un
    retournement (``Flip``) recrée toutes les couches, dans l'ordre inverse."""
    frames = simulate(geometry, [], materials, recipes)
    alive: list[Any] = list(geometry.layers)  # garde chaque couche vivante : son id() n'est jamais redonné
    origin = {id(layer): SUBSTRATE_ORIGIN for layer in geometry.layers}
    origins = [[origin[id(layer)] for layer in geometry.frame_layers()]]
    for index, step in enumerate(steps):
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
    return frames, origins


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
) -> SimulationResult:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) and which step created each layer of
    each frame, for a caller that needs them for more than just a preview (e.g. to commit the
    result as a Follow experiment). Every microproject shares the same material/step/recipe physics.

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
        frames, origins = _simulate_tracking(geometry, steps, materials, recipes)
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
LABEL_DECLARED_PREFIX = "declared:"
MAX_LABEL_TEXT = 40
MAX_LABEL_VALUES = 6


class LayerLabel(BaseModel):
    """L'étiquette d'une étape : son texte et les valeurs à écrire dessous, dans l'ordre -
    ``"thickness"``, ``"composition"`` (le taux d'In/Al d'un nitrure à composition) ou
    ``"declared:<nom>"`` (un :class:`DeclaredParam` de l'étape). Une valeur que l'étape n'a pas
    n'est simplement pas écrite."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field("", max_length=MAX_LABEL_TEXT)
    values: list[str] = Field(default_factory=list, max_length=MAX_LABEL_VALUES)

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
            if value not in (LABEL_THICKNESS, LABEL_COMPOSITION) and not declared:
                raise ValueError(f"valeur d'étiquette inconnue : {value!r} (thickness, composition ou declared:<nom>)")
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


class ProcessBrick(BaseModel):
    """Une brique du procédé : son identifiant de groupe (celui du constructeur, gardé d'une version
    à l'autre), son nom, la brique de bibliothèque d'où elle vient (``source``, son id, si on la
    connaît) et les positions de ses étapes, consécutives."""

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(pattern=BRICK_GROUP_ID_RE)
    name: str = Field(min_length=1, max_length=120)
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
