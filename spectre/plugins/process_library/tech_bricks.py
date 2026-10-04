"""Saved, reusable technology bricks: a named ordered sequence of process steps, persisted
independently of any structure or experiment - so a recurring block of process (e.g. "masque +
gravure RIE standard" or a whole epitaxial buffer stack) can be built once and inserted as a unit
wherever it's needed, instead of retyping the same handful of steps every time. Like every
library item (:mod:`spectre.plugins.process_library.service`), a brick is built in, shared across
every microproject, or private to one.

A brick is the "sequence" analog of :class:`spectre.plugins.process_library.step_presets.StepPreset`
(a single step's mode/angle/selectivity) the same way
:class:`spectre.plugins.process_library.structure_library.SavedStructure` is the
"sequence + substrate" one - it deliberately carries no substrate of its own (a brick applies on
top of whatever structure already exists) and, like both of those, is a point of departure rather
than a live link: inserting a brick copies its steps into the caller's own step list once, and
editing either afterwards never affects the other.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator
from structureforge.process.steps import ProcessStep

from ..library.service import load
from ..structures.simulation import DeclaredParam, LayerLabel, layer_labels_by_index
from .models import LibraryItem


class TechBrick(LibraryItem):
    steps: list[ProcessStep]  # no substrate - a brick applies on top of whatever already exists
    # the steps' declared parameters (see spectre.plugins.structures.simulation.DeclaredParam), by step index
    declared_params: dict[str, list[DeclaredParam]] = Field(default_factory=dict)
    # the layer labels of the chosen steps (see spectre.plugins.structures.simulation.LayerLabel), by step index
    layer_labels: dict[str, LayerLabel] = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def _labels_on_steps(self) -> "TechBrick":
        layer_labels_by_index(self.layer_labels, len(self.steps))
        return self


def default_tech_bricks() -> dict[str, TechBrick]:
    """The built-in bricks: the root library's ``briques.yml`` (declared in
    :mod:`spectre.plugins.process_library.library_files`), or :func:`builtin_tech_bricks` when it
    is missing or invalid.
    """
    return load("tech-bricks")


def tech_brick_from_entry(entry: dict[str, Any]) -> TechBrick:
    """One entry of ``briques.yml`` (``name``, ``notes``, ``steps``)."""
    return TechBrick.model_validate(
        {"name": entry["name"], "notes": entry.get("notes"), "steps": entry.get("steps") or [], "created_at": "preset"}
    )


def builtin_tech_bricks() -> dict[str, TechBrick]:
    """Fallback brick set when ``briques.yml`` is missing - empty: unlike a single step's
    mode/angle (which map cleanly onto real, universal recipe names), there's no single "standard"
    multi-step brick generic enough to bundle in code. Add bricks to ``briques.yml`` (or share
    them from the app) instead.
    """
    return {}
