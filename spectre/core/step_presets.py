"""Saved, reusable step presets: a named shortcut to one of StructureForge's own deposition/etch
recipes (see :mod:`structureforge.core.recipes`), persisted independently of any structure - handy
for a team's own vocabulary ("notre gravure standard") on top of the recipe library's own names.

Two stores per Spectre instance, the same split as :mod:`spectre.core.structure_library`: one
shared across every project, one private to a single project - see :func:`spectre.core.projects.
get_shared_step_preset_store`/``get_step_preset_store``. Applying a preset only pre-fills a step's
form fields client-side (see ``structure-builder.js``); once added, a step carries its own
``recipe`` independently, the same "point of departure, not a live link" relationship the
structure library already has between a preset structure and the experience derived from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .keyed_store import KeyedJsonStore


class DepositionPreset(BaseModel):
    kind: Literal["deposition"] = "deposition"
    recipe: str


class EtchPreset(BaseModel):
    kind: Literal["etch"] = "etch"
    recipe: str


StepPresetPayload = Annotated[Union[DepositionPreset, EtchPreset], Field(discriminator="kind")]


class StepPreset(BaseModel):
    name: str
    payload: StepPresetPayload
    notes: str | None = None
    created_at: str


class StepPresetLibrary(BaseModel):
    presets: dict[str, StepPreset] = Field(default_factory=dict)


def StepPresetStore(path: str | Path) -> KeyedJsonStore[StepPresetLibrary, StepPreset]:
    return KeyedJsonStore(path, StepPresetLibrary, "presets")


def default_step_presets() -> dict[str, StepPreset]:
    """The preset library's ``"preset"`` scope: the editable root library
    (``library/presets.yml`` via :mod:`spectre.core.registry`) when it exists, otherwise the
    built-in set below. Always available from every project, never written to a JSON store (only
    the shared/project stores are). Imported lazily to avoid a core import cycle
    (``registry`` imports this module for its models).
    """
    from .registry import registry_step_presets

    return registry_step_presets()


def _builtin_step_presets() -> dict[str, StepPreset]:
    """Fallback preset set when ``library/presets.yml`` is missing - a nitride/semiconductor-
    oriented subset (III-N epitaxy, passivation dielectrics, contact metals, the etches that go
    with them). The shipped YAML file mirrors this list; edit that file to grow it.
    """
    deposition = [
        StepPreset(
            name="ALD Conformal",
            payload=DepositionPreset(recipe="ALD Conformal"),
            notes="Dépôt uniforme qui épouse parfaitement tous les reliefs de la surface.",
            created_at="preset",
        ),
        StepPreset(
            name="PVD Sputter (tilted)",
            payload=DepositionPreset(recipe="PVD Sputter (tilted)"),
            notes="Dépôt métallique en visée directe, légèrement incliné — les zones cachées sont moins couvertes.",
            created_at="preset",
        ),
        StepPreset(
            name="Evaporation (normal)",
            payload=DepositionPreset(recipe="Evaporation (normal)"),
            notes="Dépôt métallique tout droit par le dessus — ne couvre presque pas les flancs, adapté à un lift-off.",
            created_at="preset",
        ),
        StepPreset(
            name="MOCVD Epitaxial",
            payload=DepositionPreset(recipe="MOCVD Epitaxial"),
            notes="Croissance épitaxiale (semi-conducteurs III-N/III-V) sur une base plane.",
            created_at="preset",
        ),
        StepPreset(
            name="PECVD Conformal",
            payload=DepositionPreset(recipe="PECVD Conformal"),
            notes="Dépôt assisté par plasma, à plus basse température — bonne couverture des reliefs.",
            created_at="preset",
        ),
        StepPreset(
            name="Sputter Metal (normal)",
            payload=DepositionPreset(recipe="Sputter Metal (normal)"),
            notes="Dépôt métallique par pulvérisation, par le dessus — couvre mieux les flancs qu'une évaporation, reste directionnel.",
            created_at="preset",
        ),
    ]
    etch = [
        StepPreset(
            name="Dry Oxide Etch",
            payload=EtchPreset(recipe="Dry Oxide Etch"),
            notes="Gravure sèche qui attaque surtout les oxydes ; grave presque aussi vite tout le reste.",
            created_at="preset",
        ),
        StepPreset(
            name="Wet HF Dip",
            payload=EtchPreset(recipe="Wet HF Dip"),
            notes="Bain humide très sélectif de l'oxyde — épargne le nitrure, le silicium et les métaux.",
            created_at="preset",
        ),
        StepPreset(
            name="Anisotropic RIE",
            payload=EtchPreset(recipe="Anisotropic RIE"),
            notes="Gravure sèche quasi verticale — le masque de résine s'érode lentement, tout le reste au rythme normal.",
            created_at="preset",
        ),
        StepPreset(
            name="Ion Mill (tilted)",
            payload=EtchPreset(recipe="Ion Mill (tilted)"),
            notes="Gravure physique inclinée (usinage ionique) — attaque presque tous les matériaux au même rythme.",
            created_at="preset",
        ),
        StepPreset(
            name="Cl2 ICP-RIE (III-N)",
            payload=EtchPreset(recipe="Cl2 ICP-RIE (III-N)"),
            notes="Gravure sèche quasi verticale des semi-conducteurs III-N (GaN, AlGaN...) — sélective par rapport aux masques, diélectriques et métaux.",
            created_at="preset",
        ),
        StepPreset(
            name="Wet Metal Etch",
            payload=EtchPreset(recipe="Wet Metal Etch"),
            notes="Bain humide générique pour graver un métal — attaque lentement tout le reste ; sous-grave comme toute gravure isotrope.",
            created_at="preset",
        ),
    ]
    return {p.name: p for p in [*deposition, *etch]}
