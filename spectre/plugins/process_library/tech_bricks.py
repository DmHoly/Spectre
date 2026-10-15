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
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_serializer, model_validator
from structureforge.process.steps import ProcessStep

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
    # goes up each time its content changes (BRICK_CONTENT_FIELDS): a structure's copy keeps the
    # version it was taken at (ProcessBrick.version) and can tell it has been changed since
    version: int = Field(1, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _without_the_old_macro_step(cls, data: Any) -> Any:
        # the macro-step role and preview bricks of before (removed on 2026-10-15): a brick file
        # written before the migration still carries them
        if isinstance(data, dict) and ("role" in data or "preview_on" in data):
            data = {key: value for key, value in data.items() if key not in ("role", "preview_on")}
        return data

    @model_serializer(mode="wrap")
    def _substrate_only_for_a_starting_brick(self, handler: Any) -> dict[str, Any]:
        # une brique ordinaire n'a rien d'un substrat dans sa forme (seule une brique de départ en porte un)
        data = handler(self)
        if data.get("substrate") is None:
            data.pop("substrate", None)
        return data

    @model_validator(mode="after")
    def _labels_on_steps(self) -> "TechBrick":
        layer_labels_by_index(self.layer_labels, len(self.steps))
        checked_bricks(self.bricks, len(self.steps))
        return self


# the content of a brick - what a change of makes a new version (its name, notes or scope do not)
BRICK_CONTENT_FIELDS = ("steps", "declared_params", "layer_labels", "bricks", "recipes", "preset_origins", "lattice_openings", "substrate")


def revised_brick(old: TechBrick, new: TechBrick) -> TechBrick:
    """``new``, one version above ``old`` when its content changed (:data:`BRICK_CONTENT_FIELDS`)."""
    fields = set(BRICK_CONTENT_FIELDS)
    before, after = old.model_dump(mode="json", include=fields), new.model_dump(mode="json", include=fields)
    return new.model_copy(update={"version": old.version + 1 if before != after else old.version})


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
