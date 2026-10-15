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
import os
import pickle
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal, NamedTuple

import shapely
import structureforge
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator
from shapely.affinity import translate
from structureforge.core.materials import Material, MaterialLibrary, aluminum_gan, default_library, indium_gan
from structureforge.core.recipes import DepositionMode, DepositionRecipe, EtchMode, EtchRecipe, RecipeLibrary, default_recipes
from structureforge.core.traced import Traced
from structureforge.core.units import Length
from structureforge.geometry.engine import Geometry, Layer, LayerProvenance
from structureforge.process.simulate import Frame, SimulationError, simulate
from structureforge.process.steps import Deposition, EpitaxialGrowth, Etch, Flip, GrowthOrientation, Lithography, ProcessStep

from ...kernel.db import data_dir
from ...kernel.errors import InvalidInput

MAX_LATTICE_WIRES = 50


class Lattice(BaseModel):
    """Le réseau de fils du gabarit SAG : un pas (nm) et le nombre de fils simulés. Le domaine fait
    alors ``wires * pitch`` de large, chaque fil au centre de sa maille (``(i + 0.5) * pitch``), et
    une lithographie ancrée au réseau (:class:`LatticeOpening`) y ouvre un trou par fil. Le nombre
    de fils est une vue (1 fil pour régler une épi, un pixel de 5-6 fils pour un procédé) : il ne
    change ni le pas ni les recettes, et le versionnage ne le compte pas (:func:`view_neutral_process`)."""

    model_config = ConfigDict(extra="forbid")

    pitch: float = Field(gt=0, le=1_000_000)
    wires: int = Field(1, ge=1, le=MAX_LATTICE_WIRES)


# Comment une lithographie s'ancre au réseau, et la taille qui la règle (nm) :
# - ``wires`` : un trou de ``diameter`` centré sur chaque fil (le gabarit SAG, un contact sur le fil) ;
# - ``between`` : une ouverture de ``width`` centrée entre deux fils voisins - aux bords du domaine, une
#   demi-ouverture (le réseau est périodique) ;
# - ``pixel`` : une seule ouverture sur tout le pixel, moins ``margin`` de chaque côté.
LATTICE_OPENING_SIZES = {"wires": "diameter", "between": "width", "pixel": "margin"}


class LatticeOpening(BaseModel):
    """Une lithographie ancrée au réseau du substrat (:class:`Lattice`) : ses ouvertures suivent le
    pas et le nombre de fils (:data:`LATTICE_OPENING_SIZES`), recalculées à chaque simulation.
    Rangée sur l'étape elle-même (``"lattice_opening"``), à côté de ses ouvertures résolues ; un
    trou par fil (``mode`` ``wires``) s'écrit sans son mode, la forme d'avant."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["wires", "between", "pixel"] = "wires"
    diameter: float | None = Field(None, gt=0, le=1_000_000)
    width: float | None = Field(None, gt=0, le=1_000_000)
    margin: float | None = Field(None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _sized_for_its_mode(self) -> "LatticeOpening":
        size = LATTICE_OPENING_SIZES[self.mode]
        if getattr(self, size) is None:
            raise ValueError(f"une lithographie ancrée « {self.mode} » se règle par {size}")
        for other in set(LATTICE_OPENING_SIZES.values()) - {size}:
            setattr(self, other, None)
        return self

    @model_serializer(mode="wrap")
    def _compact(self, handler: Any) -> dict[str, Any]:
        data = {key: value for key, value in handler(self).items() if value is not None}
        if data.get("mode") == "wires":
            data.pop("mode")
        return data

    @property
    def size(self) -> float:
        return getattr(self, LATTICE_OPENING_SIZES[self.mode])

    def with_size(self, value: float) -> "LatticeOpening":
        return LatticeOpening(mode=self.mode, **{LATTICE_OPENING_SIZES[self.mode]: value})


LATTICE_OPENING_KEY = "lattice_opening"


class SubstrateSpec(BaseModel):
    material: str
    domain_width: Length
    thickness: Length
    # le réseau de fils (gabarit SAG) : il fixe la largeur du domaine ; absent, la forme d'avant
    lattice: Lattice | None = None

    @model_serializer(mode="wrap")
    def _without_empty_lattice(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if data.get("lattice") is None:
            data.pop("lattice", None)
        return data


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
    from .library_files import GRADIENT_FAMILIES, gradient, materials

    base = default_library()
    # le nom nu (« InGaN », « AlGaN ») prend la couleur de son dégradé, au taux que le fichier lui donne
    generic = [base.get(family).model_copy(update={"color": gradient(family).generic_color}) for family in GRADIENT_FAMILIES if family in base]
    library = base.with_materials(*generic, *materials())
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
    from .library_files import gradient

    symbol, fraction_str = match.group(1), match.group(2)
    factory = indium_gan if symbol == "In" else aluminum_gan
    material = factory(float(fraction_str))
    if material.name != name:
        return None
    # la couleur suit le dégradé de la bibliothèque (materiaux.yml, « gradients »), pas celui de StructureForge
    return material.model_copy(update={"color": gradient(f"{symbol}GaN").color_at(float(fraction_str))})


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


# -- le réseau de fils ------------------------------------------------------------------------------
#
# Un gabarit SAG ancré sur un réseau (:class:`Lattice`) plutôt que sur des nm absolus : la largeur du
# domaine et les ouvertures des lithographies ancrées (:class:`LatticeOpening`) se recalculent depuis
# le pas et le nombre de fils. Résolu dès la lecture d'une requête (``schemas.ProcessInput``) : la
# suite (simulation, campagne, lancement, Follow) ne voit qu'un procédé ordinaire, et un procédé
# enregistré garde ses ouvertures résolues à côté de leur ancrage - toujours lisible tel quel.


def lattice_openings(lattice: Lattice, opening: LatticeOpening) -> list[tuple[float, float]]:
    """Les ouvertures d'une lithographie ancrée au réseau (voir :data:`LATTICE_OPENING_SIZES`), dans
    le domaine ``[0, wires * pitch]``. :class:`ValueError` pour une ouverture qui ne tient pas : un
    trou ou un passage aussi large que le pas, une marge qui mange tout le pixel."""
    width = lattice.pitch * lattice.wires
    if opening.mode == "pixel":
        if 2 * opening.margin >= width:
            raise ValueError(f"la marge ({opening.margin:g} nm de chaque côté) couvre tout le pixel ({width:g} nm)")
        return [(round(opening.margin, 3), round(width - opening.margin, 3))]
    if opening.size >= lattice.pitch:
        what = "le diamètre d'ouverture" if opening.mode == "wires" else "la largeur entre les fils"
        raise ValueError(f"{what} ({opening.size:g} nm) doit être plus petit que le pas du réseau ({lattice.pitch:g} nm)")
    half = opening.size / 2
    if opening.mode == "wires":
        centers = [(i + 0.5) * lattice.pitch for i in range(lattice.wires)]
    else:
        centers = [i * lattice.pitch for i in range(lattice.wires + 1)]
    pieces = [(max(0.0, c - half), min(width, c + half)) for c in centers]
    return [(round(a, 3), round(b, 3)) for a, b in pieces if b > a]


def resolve_lattice(
    substrate: SubstrateSpec, steps: list[ProcessStep], anchors: dict[int, LatticeOpening]
) -> tuple[SubstrateSpec, list[ProcessStep]]:
    """Le substrat et les étapes, le réseau appliqué : le domaine fait ``wires * pitch``, chaque
    lithographie ancrée (``anchors``, par position d'étape) a un trou par fil. Sans réseau, rien ne
    change (une lithographie ancrée garde ses ouvertures). :class:`SimulationFailedError` pour un
    trou plus large que le pas."""
    lattice = substrate.lattice
    if lattice is None:
        return substrate, steps
    substrate = substrate.model_copy(update={"domain_width": Length(value=round(lattice.pitch * lattice.wires, 3), unit="nm")})
    resolved = list(steps)
    for index, opening in sorted(anchors.items()):
        step = resolved[index] if 0 <= index < len(resolved) else None
        if not isinstance(step, Lithography):
            continue
        try:
            openings = lattice_openings(lattice, opening)
        except ValueError as exc:
            raise SimulationFailedError(f"Étape {index + 1} ({step.name}) : {exc}.") from exc
        resolved[index] = step.model_copy(update={"openings": openings})
    return substrate, resolved


def lattice_anchors_in(raw_steps: Any) -> dict[int, LatticeOpening]:
    """L'ancrage au réseau de chaque lithographie d'une liste d'étapes en JSON (une requête, un
    procédé enregistré) : la clé ``"lattice_opening"`` de l'étape, qu'un ``ProcessStep`` ignore. Un
    ancrage illisible est laissé de côté (l'étape garde ses ouvertures)."""
    anchors: dict[int, LatticeOpening] = {}
    for index, step in enumerate(raw_steps if isinstance(raw_steps, list) else []):
        raw = step.get(LATTICE_OPENING_KEY) if isinstance(step, dict) and step.get("kind") == "lithography" else None
        if isinstance(raw, dict):
            try:
                anchors[index] = LatticeOpening.model_validate(raw)
            except ValueError:
                continue
    return anchors


def view_neutral_process(process: Any) -> Any:
    """Ce que le versionnage compare d'un procédé à réseau : sans ce qui ne dépend que du nombre de
    fils vus (la largeur du domaine, ``wires``, les ouvertures des lithographies ancrées) - passer
    d'un fil à un pixel de six ne change pas la structure. Un procédé sans réseau est rendu tel quel."""
    if not isinstance(process, dict):
        return process
    substrate = process.get("substrate")
    if not isinstance(substrate, dict) or not isinstance(substrate.get("lattice"), dict):
        return process
    lattice = {key: value for key, value in substrate["lattice"].items() if key != "wires"}
    neutral_substrate = {**{key: value for key, value in substrate.items() if key != "domain_width"}, "lattice": lattice}
    steps = [
        {key: value for key, value in step.items() if key != "openings"} if isinstance(step, dict) and isinstance(step.get(LATTICE_OPENING_KEY), dict) else step
        for step in process.get("steps") or []
    ]
    return {**process, "substrate": neutral_substrate, "steps": steps}


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
# donc gardé, en mémoire du serveur (les :data:`MAX_CHECKPOINTS` derniers servis) et sur disque
# (``cache/simulations/`` du dossier de données, :data:`DISK_CHECKPOINTS_MAX_BYTES` au plus, les
# moins récemment servis effacés d'abord : un redémarrage ne perd rien, une structure enregistrée se
# rouvre sans calcul), sous une clé qui résume tout ce qui l'a produit : le moteur (les sources de
# StructureForge installées), le substrat, les bibliothèques (matériaux racine, recettes) et les
# étapes jusque-là. Une simulation repart du plus long début déjà calculé : une étiquette ou un
# paramètre déclaré ne relance rien, une retouche de l'étape k ne recalcule qu'elle et la suite, et
# les variantes d'une campagne partagent les étapes d'avant leurs facteurs. Mêmes images qu'une
# simulation complète : StructureForge ne garde rien d'autre que les couches et le plancher. Le
# disque est un à-côté : illisible ou plein, il n'empêche rien, on simule.

MAX_CHECKPOINTS = 512
DISK_CHECKPOINTS_MAX_BYTES = 1 << 30  # 1 Gio sur disque ; 0 : rien sur disque (mémoire seule)
_DISK_PRUNE_EVERY = 32  # écritures entre deux tours de ménage du dossier


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


_engine_signature: str | None = None


def engine_signature() -> str:
    """Un résumé des sources de StructureForge en service : un état gardé ne vaut que pour le moteur
    qui l'a calculé (un moteur réinstallé, ou un clone mis sur ``PYTHONPATH``, repart à vide)."""
    global _engine_signature
    if _engine_signature is None:
        root = Path(structureforge.__file__).resolve().parent
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        _engine_signature = digest.hexdigest()
    return _engine_signature


def _checkpoint_keys(substrate: SubstrateSpec, steps: list[ProcessStep], recipes: RecipeLibrary) -> list[str]:
    """La clé de l'état de départ, puis de l'état après chaque étape : chacune résume la précédente
    et l'étape, si bien que deux procédés partagent les clés de leur début commun."""
    from .library_files import materials

    context = {
        "engine": engine_signature(),
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


def _trim_memory() -> None:
    while len(_checkpoints) > MAX_CHECKPOINTS:
        _checkpoints.popitem(last=False)


def _recall(key: str) -> _Checkpoint | None:
    """L'état gardé sous ``key`` : en mémoire, sinon relu du disque (et remis en mémoire) ; ``None`` sinon."""
    with _checkpoints_lock:
        checkpoint = _checkpoints.get(key)
        if checkpoint is not None:
            _checkpoints.move_to_end(key)
            return checkpoint
    checkpoint = _disk_load(key)
    if checkpoint is not None:
        with _checkpoints_lock:
            _checkpoints[key] = checkpoint
            _checkpoints.move_to_end(key)
            _trim_memory()
    return checkpoint


def _cached_start(keys: list[str]) -> list[_Checkpoint]:
    """Les états gardés du plus long début de ``keys`` (vide : rien de gardé, pas même le départ)."""
    reached: list[_Checkpoint] = []
    for key in keys:
        checkpoint = _recall(key)
        if checkpoint is None:
            break
        reached.append(checkpoint)
    return reached


def _store(key: str, checkpoint: _Checkpoint) -> None:
    with _checkpoints_lock:
        _checkpoints[key] = checkpoint
        _checkpoints.move_to_end(key)
        _trim_memory()
    _disk_save(key, checkpoint)


def _keep(key: str, geometry: Geometry, origin: dict[int, int], frame: Frame, frame_origins: list[int]) -> None:
    _store(
        key,
        _Checkpoint(
            tuple((layer.material, layer.polygon, layer.provenance, origin[id(layer)]) for layer in geometry.layers),
            geometry.floor_nm,
            _copied_frame(frame),
            tuple(frame_origins),
        ),
    )


def clear_checkpoints() -> None:
    """Oublie tous les états gardés, en mémoire et sur disque (les tests, un ménage)."""
    with _checkpoints_lock:
        _checkpoints.clear()
    with _disk_lock:
        for path in _disk_files():
            _remove_quietly(path)


# Sur disque : un fichier par état (``<clé>.pickle``), écrit entier puis mis en place (jamais relu à
# moitié), retrouvé par sa clé ; un fichier illisible (un autre format, un disque abîmé) est effacé
# et compte pour rien. Sa date est rafraîchie à chaque lecture : le ménage efface les plus anciennes.

_disk_lock = threading.Lock()
_stores_since_prune = 0
_LOAD_ERRORS = (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError, IndexError, TypeError, ValueError)


def checkpoints_dir() -> Path:
    """Le dossier des états gardés sur disque, dans le dossier de données - jamais sauvegardé avec lui
    (:mod:`spectre.kernel.database` le laisse de côté) : tout s'y recalcule."""
    return data_dir() / "cache" / "simulations"


def _disk_files() -> list[Path]:
    try:
        return [path for path in checkpoints_dir().iterdir() if path.is_file()]
    except OSError:
        return []


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _disk_load(key: str) -> _Checkpoint | None:
    if DISK_CHECKPOINTS_MAX_BYTES <= 0:
        return None
    path = checkpoints_dir() / f"{key}.pickle"
    try:
        with path.open("rb") as file:
            checkpoint = pickle.load(file)
        if not isinstance(checkpoint, _Checkpoint):
            raise ValueError("pas un état de simulation")
    except FileNotFoundError:
        return None
    except _LOAD_ERRORS:
        _remove_quietly(path)
        return None
    try:
        os.utime(path)  # servi : parmi les derniers à effacer
    except OSError:
        pass
    return checkpoint


def _disk_save(key: str, checkpoint: _Checkpoint) -> None:
    global _stores_since_prune
    if DISK_CHECKPOINTS_MAX_BYTES <= 0:
        return
    path = checkpoints_dir() / f"{key}.pickle"
    staging = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with staging.open("wb") as file:
            pickle.dump(checkpoint, file, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(staging, path)
    except (OSError, pickle.PicklingError):
        _remove_quietly(staging)
        return
    with _disk_lock:
        _stores_since_prune += 1
        if _stores_since_prune < _DISK_PRUNE_EVERY:
            return
        _stores_since_prune = 0
    prune_checkpoints()


def prune_checkpoints() -> None:
    """Ramène le dossier sous :data:`DISK_CHECKPOINTS_MAX_BYTES`, les états les moins récemment servis
    effacés d'abord - jusqu'à 80 % de la limite, pour ne pas y revenir à chaque écriture."""
    with _disk_lock:
        entries: list[tuple[float, int, Path]] = []
        for path in _disk_files():
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        total = sum(size for _mtime, size, _path in entries)
        if total <= DISK_CHECKPOINTS_MAX_BYTES:
            return
        for _mtime, size, path in sorted(entries):
            if total <= DISK_CHECKPOINTS_MAX_BYTES * 0.8:
                break
            try:
                path.unlink()
            except OSError:
                continue  # relu par une autre requête à l'instant même : au prochain tour
            total -= size


# -- le pixel de N fils, par sa maille ---------------------------------------------------------------
#
# Les bords du domaine sont des miroirs pour StructureForge (``Geometry`` : « domain edges are
# symmetry boundaries ») : une maille d'un fil, le fil au centre, est déjà le réseau infini - et un
# pixel de N fils simulé d'un bloc est le même réseau, N fois plus large et bien plus long à
# calculer (8 fils : 9 à 10 fois le temps d'un fil, mesuré). Tant que le procédé ne voit le réseau
# que par ses mailles - des lithographies ancrées au réseau (un trou par fil, un passage entre les
# fils), des dépôts, gravures et croissances symétriques - on simule donc la maille (ce que la vue
# « 1 fil » calcule déjà : même cache) et on la répète N fois, état par état. La première étape qui
# voit le pixel entier (une ouverture sur tout le pixel, des ouvertures en nm absolus, un faisceau
# incliné, une croissance semi-polaire) et la suite se simulent sur le pixel, d'un bloc, depuis
# l'état répété. Les états répétés sont gardés comme ceux d'un bloc : la vue à N fils ne refait rien
# tant que sa maille est connue.

_TILE_GRID = 1e-6  # nm - la grille qui soude les copies d'une maille (leurs bords communs à 1 ulp près)


def periodic_prefix(
    substrate: SubstrateSpec, steps: list[ProcessStep], recipes: RecipeLibrary, anchors: dict[int, LatticeOpening] | None
) -> int:
    """Le nombre d'étapes du début de ``steps`` qui ne voient le réseau que par ses mailles (voir
    plus haut) - 0 sans réseau, pour un seul fil, ou quand ce début ne contient aucune lithographie
    ancrée (rien à gagner à répéter une maille sans motif)."""
    lattice = substrate.lattice
    if lattice is None or lattice.wires < 2:
        return 0
    anchors = anchors or {}
    count = 0
    for index, step in enumerate(steps):
        if not _periodic_step(step, index, anchors, recipes):
            break
        count += 1
    if not any(index < count for index in anchors):
        return 0
    return count


def _periodic_step(step: ProcessStep, index: int, anchors: dict[int, LatticeOpening], recipes: RecipeLibrary) -> bool:
    if isinstance(step, Lithography):
        anchor = anchors.get(index)
        return anchor is not None and anchor.mode in ("wires", "between")
    if isinstance(step, Deposition):
        recipe = recipes.deposition.get(step.recipe)
        return recipe is not None and (recipe.mode is DepositionMode.conformal or recipe.angle_deg == 0)
    if isinstance(step, Etch):
        recipe = recipes.etch.get(step.recipe)
        return recipe is not None and (recipe.mode is EtchMode.isotropic or recipe.angle_deg == 0)
    if isinstance(step, EpitaxialGrowth):
        return step.orientation is not GrowthOrientation.semi_polar
    return True  # croissance facettée, enveloppe de facettes, planarisation, chimie, retrait de résine, retournement


class _Tiler:
    """Répète un polygone de la maille sur les ``wires`` mailles du pixel - une fois par polygone
    (une couche qu'une étape ne touche pas garde son polygone d'un état à l'autre)."""

    def __init__(self, pitch: float, wires: int):
        self.offsets = [round(i * pitch, 6) for i in range(wires)]
        self.done: dict[int, Any] = {}
        self.pinned: list[Any] = []  # garde chaque polygone vu vivant : son id() n'est jamais redonné

    def __call__(self, polygon: Any) -> Any:
        tiled = self.done.get(id(polygon))
        if tiled is None:
            if polygon.is_empty:
                tiled = polygon
            else:
                tiled = shapely.union_all([translate(polygon, xoff=offset) for offset in self.offsets], grid_size=_TILE_GRID)
            self.done[id(polygon)] = tiled
            self.pinned.append(polygon)
        return tiled


def _tile_prefix(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    prefix: int,
    anchors: dict[int, LatticeOpening],
    materials: MaterialLibrary,
    recipes: RecipeLibrary,
    run_id: str | None,
    keys: list[str],
) -> None:
    """Simule la maille des ``prefix`` premières étapes (ou la reprend), et garde chaque état répété
    sur le pixel sous ``keys`` (les clés du pixel, départ compris). Ne garde rien si un état de la
    maille a été évincé entre-temps : la suite simule alors le pixel d'un bloc."""
    lattice = substrate.lattice
    cell = substrate.model_copy(update={"lattice": lattice.model_copy(update={"wires": 1})})
    cell, cell_steps = resolve_lattice(cell, list(steps[:prefix]), {index: anchor for index, anchor in anchors.items() if index < prefix})
    _simulate_tracking(cell, cell_steps, materials, recipes, run_id)
    states = _cached_start(_checkpoint_keys(cell, cell_steps, recipes))
    if len(states) != prefix + 1:
        return
    width = substrate.domain_width.to_nm()
    tile = _Tiler(lattice.pitch, lattice.wires)
    for key, state in zip(keys, states):
        frame = state.frame
        _store(
            key,
            _Checkpoint(
                tuple((material, tile(polygon), provenance, origin) for material, polygon, provenance, origin in state.layers),
                state.floor_nm,
                Frame(frame.step_index, frame.step_kind, frame.step_name, [Layer(l.material, tile(l.polygon), l.provenance) for l in frame.layers], width),
                state.frame_origins,
            ),
        )


# -- le suivi d'une simulation ----------------------------------------------------------------------
#
# Une simulation de plusieurs secondes se suit : la requête annonce un identifiant (``run``, choisi par
# la page), et chaque étape terminée est notée sous lui, en mémoire - les :data:`MAX_TRACKED_RUNS`
# dernières simulations. Une étape reprise d'un état gardé (voir plus haut) compte comme faite d'emblée
# (``resumed``). Le plugin ``simulation_progress`` en fait une barre de chargement ; rien de ce qui est
# calculé n'en dépend, et sans identifiant rien n'est noté.

MAX_TRACKED_RUNS = 64
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class RunProgress(NamedTuple):
    """Où en est une simulation : ``done`` étapes faites sur ``total`` (dont ``resumed`` reprises sans
    calcul), l'étape en cours (sa position à partir de 0, son nom ; ``None`` avant la première et après
    la dernière), et l'heure de départ et de fin (``time.monotonic``)."""

    state: Literal["running", "done", "failed"]
    total: int
    done: int
    resumed: int
    step_index: int | None
    step_name: str | None
    started: float
    ended: float | None

    @property
    def elapsed(self) -> float:
        """Les secondes écoulées depuis le départ, jusqu'à la fin si elle a eu lieu."""
        return (self.ended if self.ended is not None else time.monotonic()) - self.started


_runs: OrderedDict[str, RunProgress] = OrderedDict()
_runs_lock = threading.Lock()


def run_progress(run_id: str) -> RunProgress | None:
    """L'avancement de la simulation ``run_id`` - ``None`` : inconnue, pas encore partie ou déjà oubliée."""
    with _runs_lock:
        return _runs.get(run_id)


def _start_run(run_id: str | None, total: int) -> None:
    if run_id is None:
        return
    with _runs_lock:
        _runs[run_id] = RunProgress("running", total, 0, 0, None, None, time.monotonic(), None)
        _runs.move_to_end(run_id)
        while len(_runs) > MAX_TRACKED_RUNS:
            _runs.popitem(last=False)


def _note_run(run_id: str | None, **changes: Any) -> None:
    if run_id is None:
        return
    with _runs_lock:
        current = _runs.get(run_id)
        if current is not None:
            _runs[run_id] = current._replace(**changes)


def _simulate_tracking(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    materials: MaterialLibrary,
    recipes: RecipeLibrary,
    run_id: str | None = None,
    anchors: dict[int, LatticeOpening] | None = None,
) -> tuple[Geometry, list[Frame], list[list[int]]]:
    """``structureforge.process.simulate.simulate``, une étape à la fois - mêmes images, mêmes
    erreurs - pour savoir quelle étape a créé chaque couche. StructureForge ne le dit que pour une
    croissance (``LayerProvenance``, sans la position de l'étape) : on suit donc les couches de la
    géométrie elles-mêmes, entre deux étapes. Une couche y garde son objet tant qu'elle existe (une
    gravure change son contour, pas l'objet) ; une étape ajoute les siennes à la fin ; un
    retournement (``Flip``) recrée toutes les couches, dans l'ordre inverse. Repart du plus long
    début déjà simulé (voir plus haut), et garde chaque état atteint. Un pixel de plusieurs fils
    dont le début ne voit le réseau que par ses mailles (``anchors`` : les lithographies ancrées,
    :func:`periodic_prefix`) part de sa maille répétée plutôt que de le simuler d'un bloc."""
    keys = _checkpoint_keys(substrate, steps, recipes)
    reached = _cached_start(keys)
    prefix = periodic_prefix(substrate, steps, recipes, anchors)
    tiled = bool(prefix) and prefix >= len(reached)  # le début gardé du pixel ne couvre pas ce que sa maille donne
    if tiled:
        _tile_prefix(substrate, steps, prefix, anchors or {}, materials, recipes, run_id, keys[: prefix + 1])
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
    # les états d'une maille qui vient d'être simulée sont faits, pas repris : sa simulation l'a noté
    _note_run(run_id, done=len(frames) - 1, **({} if tiled else {"resumed": len(frames) - 1}))
    for index in range(len(frames) - 1, len(steps)):
        step = steps[index]
        before = list(geometry.layers)
        _note_run(run_id, step_index=index, step_name=step.name)
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
        _note_run(run_id, done=index + 1)
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
    run_id: str | None = None,
    lattice_anchors: dict[int, LatticeOpening] | None = None,
) -> SimulationResult:
    """Build the starting geometry and apply ``steps`` to it, the same way
    ``structureforge.api.app`` does for its own ``/api/simulate`` - returns the live objects
    (geometry, one frame per step, the material library used) and which step created each layer of
    each frame, for a caller that needs them for more than just a preview (e.g. to commit the
    result as a Follow experiment). Every microproject shares the same material/step/recipe physics.

    ``declared_params`` (step_index -> extra parameters the user attached in the builder, see
    :class:`DeclaredParam`) is Spectre-only bookkeeping never seen by ``structureforge`` itself -
    it's merged onto the resulting layers' ``provenance`` after simulation succeeds. ``recipes``:
    the process's own (:class:`ProcessRecipes`), on top of the library's. ``run_id``: the simulation's
    identifier when someone follows it (:func:`run_progress`). ``lattice_anchors``: the lithographies
    anchored to the substrate's lattice, by step position - with them, a pixel of several wires is
    simulated by its cell, repeated, as far as the process only sees the lattice through its cells
    (:func:`periodic_prefix`); without them, a pixel is simulated as one block.
    """
    steps = _expand_seed_material_aliases(steps, substrate.material)
    materials = materials_library(substrate.material, *_material_names_in_steps(steps))
    recipe_library = recipes_library(recipes)
    try:
        materials.get(substrate.material)
    except KeyError as exc:
        raise SimulationFailedError(str(exc)) from exc

    _start_run(run_id, len(steps))
    state = "failed"
    try:
        geometry, frames, origins = _simulate_tracking(substrate, steps, materials, recipe_library, run_id, lattice_anchors)
        state = "done"
    except SimulationError as exc:
        raise SimulationFailedError(str(exc)) from exc
    finally:
        _note_run(run_id, state=state, step_index=None, step_name=None, ended=time.monotonic())
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
    lattice_anchors: dict[int, LatticeOpening] | None = None,
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
    by step index). A lithography anchored to the substrate's lattice (:class:`LatticeOpening`) keeps
    its anchor on the step itself (``"lattice_opening"``), next to its resolved openings.
    """
    steps_json = [step.model_dump(mode="json") for step in steps]
    for index, anchor in (lattice_anchors or {}).items():
        if 0 <= index < len(steps_json) and steps_json[index].get("kind") == "lithography":
            steps_json[index][LATTICE_OPENING_KEY] = anchor.model_dump(mode="json")
    process: dict[str, Any] = {
        "substrate": substrate.model_dump(mode="json"),
        "steps": steps_json,
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
    # la version de la brique de bibliothèque (``source``) quand on l'a copiée : une trace, jamais un
    # lien - le constructeur dit si elle a changé depuis ; absente, la forme d'avant
    version: int | None = Field(None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _without_the_old_role(cls, data: Any) -> Any:
        # le rôle de macro-étape d'avant (gabarit SAG, épitaxie, procédé - retiré le 2026-10-15) :
        # une brique enregistrée avant en porte encore un, qui ne veut plus rien dire
        if isinstance(data, dict) and "role" in data:
            data = {key: value for key, value in data.items() if key != "role"}
        return data

    @model_serializer(mode="wrap")
    def _without_empty_version(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if data.get("version") is None:
            data.pop("version", None)
        return data

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
        {
            "group_id": brick.group_id,
            "name": brick.name,
            "source": brick.source,
            "step_ids": [step_ids[i] for i in brick.step_indexes],
            **({"version": brick.version} if brick.version else {}),
        }
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
            version = item.get("version") if isinstance(item.get("version"), int) and item.get("version") >= 1 else None
            bricks.append(ProcessBrick(group_id=item.get("group_id"), name=item.get("name"), source=item.get("source"), step_indexes=indexes, version=version))
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
