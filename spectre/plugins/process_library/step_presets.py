"""Saved, reusable step presets: one whole step, already set up - a selective etch of one material,
a pyramid growth with its rates and doping, a chemical clean with its bath and duration - persisted
independently of any structure and inserted in one click from the builder's palette.

A preset holds the step itself (any kind, every field), its declared parameters (flows, doping,
temperature... :class:`~spectre.plugins.structures.simulation.DeclaredParam`), its label on the
drawing (:class:`~spectre.plugins.structures.simulation.LayerLabel`, an interface mark for a step
that makes no layer), the process recipe it names if it defines its own
(:class:`~spectre.plugins.structures.simulation.ProcessRecipes`: the selectivity of a selective
etch), and the fields worth varying in a campaign (``variable_fields``: ``"thickness"``,
``"declared:dopage"``...). Its ``version`` goes up each time its content changes.

Like every library item (:mod:`spectre.plugins.process_library.service`), a preset is built in,
shared across every microproject, or private to one. Inserting it copies the step into the process
(``structures/static/builder/presets.js``): the step then lives its own life, remembering only which
preset and which version it came from (:class:`~spectre.plugins.structures.simulation.PresetOrigin`)
- a later edit of the preset never changes a structure already built with it.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, TypeAdapter, field_validator, model_validator
from structureforge.process.steps import ProcessStep

from ..library.service import load
from ..structures.simulation import LABEL_DECLARED_PREFIX, DeclaredParam, LayerLabel, ProcessRecipes
from .models import LibraryItem

# the content of a preset - what a change of makes a new version (its name, notes or scope do not)
CONTENT_FIELDS = ("step", "declared_params", "layer_label", "recipes", "variable_fields")
# a step's fields that are never varied in a campaign (see structures.campaigns._variable_fields)
_NOT_VARIABLE = {"kind", "name", "description", "parameters", "seed_materials", "openings"}
MAX_VARIABLE_FIELDS = 12

_STEP: TypeAdapter[ProcessStep] = TypeAdapter(ProcessStep)


class StepPreset(LibraryItem):
    step: ProcessStep
    declared_params: list[DeclaredParam] = Field(default_factory=list)
    layer_label: LayerLabel | None = None
    recipes: ProcessRecipes = Field(default_factory=ProcessRecipes)
    variable_fields: list[str] = Field(default_factory=list, max_length=MAX_VARIABLE_FIELDS)
    notes: str | None = None
    version: int = Field(1, ge=1)

    @field_validator("variable_fields")
    @classmethod
    def _unique(cls, fields: list[str]) -> list[str]:
        return list(dict.fromkeys(field.strip() for field in fields if field.strip()))

    @model_validator(mode="after")
    def _variable_fields_exist(self) -> "StepPreset":
        declared = {param.name for param in self.declared_params}
        own = set(type(self.step).model_fields) - _NOT_VARIABLE
        for field in self.variable_fields:
            name = field[len(LABEL_DECLARED_PREFIX) :] if field.startswith(LABEL_DECLARED_PREFIX) else None
            if (name is not None and name not in declared) or (name is None and field not in own):
                raise ValueError(f"paramètre à faire varier inconnu pour cette étape : {field!r}")
        return self


def revised(old: StepPreset, new: StepPreset) -> StepPreset:
    """``new``, one version above ``old`` when its content changed (:data:`CONTENT_FIELDS`)."""
    before, after = old.model_dump(mode="json", include=set(CONTENT_FIELDS)), new.model_dump(mode="json", include=set(CONTENT_FIELDS))
    return new.model_copy(update={"version": old.version + 1}) if before != after else new.model_copy(update={"version": old.version})


def default_step_presets() -> dict[str, StepPreset]:
    """The built-in presets: the root library's ``presets.yml`` (declared in
    :mod:`spectre.plugins.process_library.library_files`), or the set below when it is missing or
    invalid. Always available, never written to a JSON store.
    """
    return load("step-presets")


def legacy_step(name: str, kind: str, recipe: str) -> dict[str, Any]:
    """The step of a preset from before whole-step presets, which only named a recipe: that recipe,
    with the builder's defaults for the rest."""
    if kind == "deposition":
        return {"kind": "deposition", "name": name, "material": "SiO2", "recipe": recipe, "thickness": {"value": 20, "unit": "nm"}}
    if kind == "etch":
        return {"kind": "etch", "name": name, "recipe": recipe, "depth": {"value": 10, "unit": "nm"}}
    raise ValueError(f"type de préset inconnu : {kind!r} (attendu deposition ou etch)")


def step_preset_from_entry(entry: dict[str, Any]) -> StepPreset:
    """One entry of ``presets.yml``: ``name``, ``step`` (the step, ``kind`` included; its ``name``
    defaults to the preset's), and optionally ``declared_params``, ``label`` (``{text, values}``),
    ``recipe`` (the process recipe the step names - an etch one when it has a selectivity table),
    ``variable`` (the fields worth varying) and ``notes``. An entry of the former shape (``kind`` +
    ``recipe`` only) still reads, with the builder's defaults for the rest."""
    name = entry["name"]
    if "step" in entry:
        step = {"name": name, **entry["step"]}
    else:
        step = legacy_step(name, entry.get("kind", ""), entry["recipe"])
    recipes: dict[str, list[Any]] = {}
    own = entry.get("recipe") if "step" in entry else None
    if isinstance(own, dict):
        recipes[step["kind"]] = [{"name": step.get("recipe") or name, **own}]
        step.setdefault("recipe", recipes[step["kind"]][0]["name"])
    return StepPreset(
        name=name,
        step=_STEP.validate_python(step),
        declared_params=entry.get("declared_params") or [],
        layer_label=entry.get("label"),
        recipes=ProcessRecipes.model_validate(recipes),
        variable_fields=entry.get("variable") or [],
        notes=entry.get("notes"),
        created_at="preset",
    )


def builtin_step_presets() -> dict[str, StepPreset]:
    """Fallback preset set when ``presets.yml`` is missing - a few nitride-oriented examples of
    each kind of preset. The shipped YAML file holds the full set; edit that file to grow it."""
    entries = [
        {
            "name": "Gravure sélective Al2O3",
            "step": {"kind": "etch", "recipe": "Gravure sélective Al2O3", "depth": {"value": 50, "unit": "nm"}},
            "recipe": {"mode": "isotropic", "selectivity_by_material": {"Al2O3": 1.0}, "default_factor": 0.0},
            "declared_params": [{"name": "durée", "value": 120, "unit": "s"}],
            "label": {"text": "", "values": ["declared:durée"]},
            "variable": ["declared:durée"],
            "notes": "Ne grave que l'Al2O3 : tout le reste sert de couche d'arrêt.",
        },
        {
            "name": "Pyramide GaN",
            "step": {
                "kind": "faceted_growth",
                "material": "GaN",
                "thickness": {"value": 200, "unit": "nm"},
                "rate_c": 0.2,
                "rate_m": 0.1,
                "rate_sp": 1.0,
                "semi_polar_angle_deg": 28,
            },
            "declared_params": [{"name": "température", "value": 1000, "unit": "°C"}, {"name": "V/III", "value": 2000}],
            "label": {"text": "", "values": ["thickness"]},
            "variable": ["thickness", "rate_sp", "declared:température"],
            "notes": "Croissance facettée où le semipolaire domine : la pointe se referme en pyramide.",
        },
        {
            "name": "Clean HF",
            "step": {"kind": "chemical", "description": "HF dilué"},
            "declared_params": [{"name": "durée", "value": 30, "unit": "s"}, {"name": "concentration", "value": 1, "unit": "%"}],
            "label": {"text": "", "values": ["declared:durée"]},
            "variable": ["declared:durée"],
            "notes": "Désoxydation avant reprise de croissance.",
        },
    ]
    return {preset.name: preset for preset in map(step_preset_from_entry, entries)}
