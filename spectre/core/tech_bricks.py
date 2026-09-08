"""Saved, reusable technology bricks: a named ordered sequence of process steps, persisted
independently of any structure or experiment - so a recurring block of process (e.g. "masque +
gravure RIE standard" or a whole epitaxial buffer stack) can be built once and inserted as a unit
wherever it's needed, instead of retyping the same handful of steps every time. Two stores per
Spectre instance, the same split as :mod:`spectre.core.structure_library`/:mod:`spectre.core.
step_presets`: one shared across every project, one private to a single project - see
:func:`spectre.core.projects.get_shared_tech_brick_store`/``get_tech_brick_store``.

A brick is the "sequence" analog of :class:`spectre.core.step_presets.StepPreset` (a single step's
mode/angle/selectivity) the same way :class:`spectre.core.structure_library.SavedStructure` is the
"sequence + substrate" one - it deliberately carries no substrate of its own (a brick applies on
top of whatever structure already exists) and, like both of those, is a point of departure rather
than a live link: inserting a brick copies its steps into the caller's own step list once, and
editing either afterwards never affects the other.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from structureforge.process.steps import ProcessStep

from .keyed_store import KeyedJsonStore


class TechBrick(BaseModel):
    name: str
    steps: list[ProcessStep]  # no substrate - a brick applies on top of whatever already exists
    notes: str | None = None
    created_at: str


class TechBrickLibrary(BaseModel):
    bricks: dict[str, TechBrick] = Field(default_factory=dict)


def TechBrickStore(path: str | Path) -> KeyedJsonStore[TechBrickLibrary, TechBrick]:
    return KeyedJsonStore(path, TechBrickLibrary, "bricks")


def default_tech_bricks() -> dict[str, TechBrick]:
    """The brick library's ``"preset"`` scope: the editable root library
    (``library/briques.yml`` via :mod:`spectre.core.registry`) when it exists, otherwise
    :func:`_builtin_tech_bricks`. Imported lazily to avoid a core import cycle.
    """
    from .registry import registry_tech_bricks

    return registry_tech_bricks()


def _builtin_tech_bricks() -> dict[str, TechBrick]:
    """Fallback brick set when ``library/briques.yml`` is missing - empty: unlike a single step's
    mode/angle (which map cleanly onto real, universal recipe names), there's no single "standard"
    multi-step brick generic enough to bundle in code. Add bricks to ``library/briques.yml`` (or a
    project's / the shared store) instead.
    """
    return {}
