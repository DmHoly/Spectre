"""Saved, reusable technology bricks: a named ordered sequence of process steps, persisted
independently of any structure or experiment - so a recurring block of process (e.g. "masque +
gravure RIE standard" or a whole epitaxial buffer stack) can be built once and inserted as a unit
wherever it's needed, instead of retyping the same handful of steps every time. Like every
library item (:mod:`spectre.plugins.process_library.service`), a brick is built in, shared across
every microproject, or private to one.

A brick is the "sequence" analog of :class:`spectre.plugins.process_library.step_presets.StepPreset`
(a single step's mode/angle/selectivity) the same way
:class:`spectre.plugins.process_library.structure_library.SavedStructure` is the
"sequence + substrate" one. A brick applies on top of whatever structure already exists; a
**starting brick** also keeps a substrate (with its lattice of wires, for a SAG template), taken
only when the brick is inserted in an empty structure. Like both of those, a brick is a point of
departure rather than a live link: inserting a brick copies its steps into the caller's own step
list once, and editing either afterwards never affects the other.

**Versions.** A brick's content (:data:`BRICK_CONTENT_FIELDS`) is numbered ``MAJOR.MINOR`` by the
rule of the studies (:func:`spectre.plugins.experiments.versioning.classify_process_change`): a
step added, removed or moved, or the substrate changed, opens ``X+1.0``; a parameter changed
(declared ones included, the brick's own recipes, an anchor on the lattice) gives ``X.Y+1``; a
step renamed, a layer label, a preset trace is a *retouche* that keeps the number. Every numbered
version is kept with the brick (:class:`BrickVersion`: the number, when, who, why and the content
of then), so its evolution can be read; a structure's copy keeps the number it was taken at
(:class:`~spectre.plugins.structures.simulation.ProcessBrick`).

**Reference brick.** A shared brick promoted as a reference (:class:`BrickReference`, through the
promotion plugin, the only path): the one whose evolution people follow, listed on ``/briques``.
A new version of a reference brick needs a note (why this version).
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from structureforge.process.steps import ProcessStep

from ...kernel.errors import InvalidInput
from ..experiments.versioning import classify_process_change
from ..library.service import load
from ..structures.simulation import (
    DeclaredParam,
    LatticeOpening,
    LayerLabel,
    PresetOrigin,
    ProcessBrick,
    ProcessRecipes,
    SubstrateSpec,
    checked_bricks,
    layer_labels_by_index,
)
from .models import LibraryItem

BRICK_VERSION_RE = re.compile(r"^([1-9][0-9]{0,4})\.([0-9]{1,5})$")
BRICK_VERSION_PATTERN = BRICK_VERSION_RE.pattern
FIRST_BRICK_VERSION = "1.0"
NOTE_MAX_LENGTH = 2000

BrickChangeLevel = Literal["initial", "major", "minor", "patch", "none"]
BRICK_LEVEL_TEXT = {"initial": "première version", "major": "changement majeur", "minor": "changement mineur", "patch": "retouche", "none": "sans changement"}


def brick_version_text(version: Any) -> str | None:
    """A brick version as kept today (``"1.2"``) - an integer ``N`` of before the numbering (the
    counter of 2026-10-10) reads as ``"N.0"`` ; anything else is no version."""
    if isinstance(version, bool):
        return None
    if isinstance(version, int) and version >= 1:
        return f"{version}.0"
    if isinstance(version, str) and BRICK_VERSION_RE.match(version):
        return version
    return None


def version_key(number: str) -> tuple[int, int]:
    major, minor = number.split(".")
    return int(major), int(minor)


class BrickVersion(BaseModel):
    """One numbered version of a brick: its number, when and by whom it was made, why (the note,
    required for a reference brick), the change it made (``level``) and the content of the brick
    then (:data:`BRICK_CONTENT_FIELDS`, as JSON)."""

    model_config = ConfigDict(extra="forbid")

    number: str = Field(pattern=BRICK_VERSION_PATTERN)
    created_at: str
    created_by: int | None = None
    note: str = Field("", max_length=NOTE_MAX_LENGTH)
    level: BrickChangeLevel = "initial"
    content: dict[str, Any] = Field(default_factory=dict)


class BrickReference(BaseModel):
    """What makes a brick a reference brick: who promoted it, when, and why."""

    model_config = ConfigDict(extra="forbid")

    promoted_by: int | None = None
    promoted_at: str
    note: str = Field("", max_length=NOTE_MAX_LENGTH)


class TechBrick(LibraryItem):
    steps: list[ProcessStep]  # a brick applies on top of whatever already exists
    # a starting brick's own substrate (with its lattice of wires): the start of a structure built
    # on it, taken only when the brick is inserted in an empty structure. Absent, the brick only
    # applies on top of an existing structure
    substrate: SubstrateSpec | None = None
    # the steps' declared parameters (see spectre.plugins.structures.simulation.DeclaredParam), by step index
    declared_params: dict[str, list[DeclaredParam]] = Field(default_factory=dict)
    # the layer labels of the chosen steps (see spectre.plugins.structures.simulation.LayerLabel), by step index
    layer_labels: dict[str, LayerLabel] = Field(default_factory=dict)
    # the bricks its own steps belong to (a brick composed with another inserted in it, see
    # spectre.plugins.structures.simulation.ProcessBrick), by step index
    bricks: list[ProcessBrick] = Field(default_factory=list)
    # the process's own recipes (see spectre.plugins.structures.simulation.ProcessRecipes)
    recipes: ProcessRecipes = Field(default_factory=ProcessRecipes)
    # the step preset each step was inserted from (see spectre.plugins.structures.simulation.PresetOrigin), by step index
    preset_origins: dict[str, PresetOrigin] = Field(default_factory=dict)
    # the lithographies anchored to the substrate's lattice (see spectre.plugins.structures.simulation.LatticeOpening), by step index
    lattice_openings: dict[str, LatticeOpening] = Field(default_factory=dict)
    notes: str | None = None
    # the number of its current content ("1.2"), and every numbered version, the oldest first: a
    # structure's copy keeps the number it was taken at (ProcessBrick.version) and can tell the
    # brick has changed since
    version: str = Field(FIRST_BRICK_VERSION, pattern=BRICK_VERSION_PATTERN)
    versions: list[BrickVersion] = Field(default_factory=list)
    # a reference brick (promoted through the promotion plugin) ; None, an ordinary brick
    reference: BrickReference | None = None

    @model_validator(mode="before")
    @classmethod
    def _the_forms_of_before(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # the macro-step role and preview bricks of before (removed on 2026-10-15): a brick file
        # written before the migration still carries them
        data = {key: value for key, value in data.items() if key not in ("role", "preview_on")}
        # the integer counter of before the X.Y numbers : N reads as N.0
        if isinstance(data.get("version"), int) and not isinstance(data.get("version"), bool):
            data["version"] = f"{data['version']}.0"
        return data

    @model_serializer(mode="wrap")
    def _without_the_empty_fields(self, handler: Any) -> dict[str, Any]:
        # une brique ordinaire n'a rien d'un substrat dans sa forme (seule une brique de départ en
        # porte un), ni de référence
        data = handler(self)
        for key in ("substrate", "reference"):
            if key in data and data[key] is None:
                data.pop(key)
        return data

    @model_validator(mode="after")
    def _checked(self) -> "TechBrick":
        layer_labels_by_index(self.layer_labels, len(self.steps))
        checked_bricks(self.bricks, len(self.steps))
        if not self.versions:
            # a brick from before the numbered versions (or just created) : its current content is
            # its first kept version
            self.versions = [BrickVersion(number=self.version, created_at=self.created_at, created_by=self.created_by, level="initial", content=self.content())]
        return self

    def content(self) -> dict[str, Any]:
        """The content of the brick (:data:`BRICK_CONTENT_FIELDS`), as JSON - what a version keeps
        and what a change of makes a new version."""
        return self.model_dump(mode="json", include=set(BRICK_CONTENT_FIELDS))

    @property
    def is_reference(self) -> bool:
        return self.reference is not None


# the content of a brick - what a change of makes a new version (its name, notes or scope do not)
BRICK_CONTENT_FIELDS = ("steps", "declared_params", "layer_labels", "bricks", "recipes", "preset_origins", "lattice_openings", "substrate")


def brick_change_level(before: dict[str, Any], after: dict[str, Any]) -> BrickChangeLevel:
    """What the change from the content ``before`` to ``after`` is worth (both :meth:`TechBrick.content`):
    the rule of the studies - ``major`` for the substrate or the shape of the steps, ``minor`` for a
    parameter (a declared one, the brick's own recipes or an anchor on the lattice included),
    ``patch`` for a name, a label or a trace, ``none`` for the same content."""
    if before == after:
        return "none"
    shape = lambda content: {key: content.get(key) for key in ("substrate", "steps", "declared_params") if content.get(key) is not None}
    level = classify_process_change(shape(before), shape(after))
    if level in ("major", "minor"):
        return level
    if before.get("recipes") != after.get("recipes") or before.get("lattice_openings") != after.get("lattice_openings"):
        return "minor"
    return "patch"


def next_brick_version(number: str, level: BrickChangeLevel) -> str:
    major, minor = version_key(number)
    if level == "major":
        return f"{major + 1}.0"
    if level == "minor":
        return f"{major}.{minor + 1}"
    return number


def revised_brick(old: TechBrick, new: TechBrick, *, user_id: int | None = None, note: str | None = None) -> TechBrick:
    """``new``, numbered after ``old`` : a new version (kept with its note) when the content changed
    by a major or minor step, the current version's content refreshed for a retouche, nothing for
    a change of name, notes or scope. A reference brick does not take a new version without a
    note (422 ``brick_note_required``)."""
    from .service import _now  # the clock of the library's writes

    before, after = old.content(), new.content()
    level = brick_change_level(before, after)
    versions = [version.model_copy() for version in old.versions]
    if level == "none":
        return new.model_copy(update={"version": old.version, "versions": versions, "reference": old.reference})
    note = (note or "").strip()
    if level in ("major", "minor"):
        if old.is_reference and not note:
            raise InvalidInput("Une brique de référence ne change pas sans dire pourquoi : donnez une note à cette version.", code="brick_note_required")
        number = next_brick_version(old.version, level)
        versions.append(BrickVersion(number=number, created_at=_now(), created_by=user_id, note=note, level=level, content=after))
        return new.model_copy(update={"version": number, "versions": versions, "reference": old.reference})
    # a retouche : the current number keeps, its kept content follows
    if versions and versions[-1].number == old.version:
        versions[-1] = versions[-1].model_copy(update={"content": after})
    return new.model_copy(update={"version": old.version, "versions": versions, "reference": old.reference})


# -- ce qui change d'une version à l'autre ---------------------------------------------------------


def _length_text(value: Any) -> str:
    if isinstance(value, dict) and "value" in value and "unit" in value:
        unit = {"um": "µm", "A": "Å"}.get(value["unit"], value["unit"])
        return f"{value['value']:g} {unit}" if isinstance(value["value"], (int, float)) else f"{value['value']} {unit}"
    if isinstance(value, list):
        return "[" + ", ".join(_length_text(v) for v in value) + "]"
    if isinstance(value, dict):
        return ", ".join(f"{k} {_length_text(v)}" for k, v in value.items())
    if value is None:
        return "—"
    return f"{value:g}" if isinstance(value, float) else str(value)


def _step_label(step: dict[str, Any]) -> str:
    return str(step.get("name") or step.get("kind") or "étape")


def _substrate_text(substrate: dict[str, Any] | None) -> str:
    if not substrate:
        return "aucun"
    lattice = substrate.get("lattice")
    text = f"{substrate.get('material', '?')} {_length_text(substrate.get('thickness'))}"
    if isinstance(lattice, dict):
        return f"{text}, réseau au pas de {_length_text(lattice.get('pitch'))} nm"
    return f"{text}, {_length_text(substrate.get('domain_width'))} de large"


def _declared_text(params: Any) -> str:
    if not isinstance(params, list):
        return "—"
    return ", ".join(f"{p.get('name')} = {_length_text(p.get('value'))}{' ' + p['unit'] if p.get('unit') else ''}" for p in params if isinstance(p, dict)) or "aucun"


def brick_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What changed from the content ``before`` to ``after``, in words - one line per change : the
    substrate, each step added, removed, replaced or whose fields changed, the declared
    parameters, the brick's own recipes, the anchors, the labels."""
    lines: list[str] = []
    if before.get("substrate") != after.get("substrate"):
        lines.append(f"Substrat : {_substrate_text(before.get('substrate'))} → {_substrate_text(after.get('substrate'))}")
    old_steps, new_steps = before.get("steps") or [], after.get("steps") or []
    old_keys, new_keys = [(s.get("kind"), s.get("name")) for s in old_steps], [(s.get("kind"), s.get("name")) for s in new_steps]
    if [k for k, _ in old_keys] == [k for k, _ in new_keys]:
        for index, (old, new) in enumerate(zip(old_steps, new_steps)):
            if old == new:
                continue
            if old.get("name") != new.get("name"):
                lines.append(f"Étape {index + 1} renommée : « {_step_label(old)} » → « {_step_label(new)} »")
            for field in sorted(set(old) | set(new)):
                if field == "name" or old.get(field) == new.get(field):
                    continue
                lines.append(f"« {_step_label(new)} » : {field} {_length_text(old.get(field))} → {_length_text(new.get(field))}")
    else:
        matcher = difflib.SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            removed, added = old_steps[i1:i2], new_steps[j1:j2]
            if tag == "replace" and len(removed) == len(added):
                for old, new in zip(removed, added):
                    lines.append(f"Étape remplacée : « {_step_label(old)} » → « {_step_label(new)} »")
                continue
            lines.extend(f"Étape retirée : « {_step_label(s)} »" for s in removed)
            lines.extend(f"Étape ajoutée : « {_step_label(s)} »" for s in added)
    old_declared, new_declared = before.get("declared_params") or {}, after.get("declared_params") or {}
    for key in sorted(set(old_declared) | set(new_declared), key=lambda k: int(k) if str(k).isdigit() else 0):
        if old_declared.get(key) == new_declared.get(key):
            continue
        step = new_steps[int(key)] if str(key).isdigit() and int(key) < len(new_steps) else {}
        lines.append(f"Paramètres déclarés de « {_step_label(step)} » : {_declared_text(old_declared.get(key))} → {_declared_text(new_declared.get(key))}")
    if before.get("recipes") != after.get("recipes"):
        lines.append("Recettes propres de la brique modifiées")
    if before.get("lattice_openings") != after.get("lattice_openings"):
        lines.append("Ancrage au réseau de fils modifié")
    if before.get("layer_labels") != after.get("layer_labels"):
        lines.append("Étiquettes de couches modifiées")
    if before.get("preset_origins") != after.get("preset_origins") or before.get("bricks") != after.get("bricks"):
        lines.append("Trace des présets ou des briques internes modifiée")
    return lines


def default_tech_bricks() -> dict[str, TechBrick]:
    """The built-in bricks: the root library's ``briques.yml`` (declared in
    :mod:`spectre.plugins.process_library.library_files`), or :func:`builtin_tech_bricks` when it
    is missing or invalid.
    """
    return load("tech-bricks")


def tech_brick_from_entry(entry: dict[str, Any]) -> TechBrick:
    """One entry of ``briques.yml`` (``name``, ``notes``, ``steps``; ``substrate`` and
    ``lattice_openings`` for a starting brick)."""
    return TechBrick.model_validate(
        {
            "name": entry["name"],
            "notes": entry.get("notes"),
            "steps": entry.get("steps") or [],
            "substrate": entry.get("substrate"),
            "lattice_openings": entry.get("lattice_openings") or {},
            "created_at": "preset",
        }
    )


def builtin_tech_bricks() -> dict[str, TechBrick]:
    """Fallback brick set when ``briques.yml`` is missing - empty: unlike a single step's
    mode/angle (which map cleanly onto real, universal recipe names), there's no single "standard"
    multi-step brick generic enough to bundle in code. Add bricks to ``briques.yml`` (or share
    them from the app) instead.
    """
    return {}
