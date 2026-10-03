"""Saved, reusable step presets: a named shortcut to one of StructureForge's own deposition/etch
recipes (see :mod:`structureforge.core.recipes`), persisted independently of any structure - handy
for a team's own vocabulary ("notre gravure standard") on top of the recipe library's own names.

Like every library item (:mod:`spectre.plugins.process_library.service`), a preset is built in,
shared across every microproject, or private to one. Applying a preset only pre-fills a step's
form fields client-side (see ``structures/static/builder/form-widgets.js``); once added, a step carries its own
``recipe`` independently, the same "point of departure, not a live link" relationship the
structure library already has between a preset structure and the experience derived from it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from ..library.service import load
from .models import LibraryItem


class DepositionPreset(BaseModel):
    kind: Literal["deposition"] = "deposition"
    recipe: str


class EtchPreset(BaseModel):
    kind: Literal["etch"] = "etch"
    recipe: str


StepPresetPayload = Annotated[Union[DepositionPreset, EtchPreset], Field(discriminator="kind")]


class StepPreset(LibraryItem):
    payload: StepPresetPayload
    notes: str | None = None


def default_step_presets() -> dict[str, StepPreset]:
    """The built-in presets: the root library's ``presets.yml`` (declared in
    :mod:`spectre.plugins.process_library.library_files`), or the set below when it is missing or
    invalid. Always available, never written to a JSON store.
    """
    return load("step-presets")


def step_preset_from_entry(entry: dict[str, Any]) -> StepPreset:
    """One entry of ``presets.yml`` (``name``, ``kind``, ``recipe``, ``notes``)."""
    kind = entry["kind"]
    if kind == "deposition":
        payload: DepositionPreset | EtchPreset = DepositionPreset(recipe=entry["recipe"])
    elif kind == "etch":
        payload = EtchPreset(recipe=entry["recipe"])
    else:
        raise ValueError(f"type de préset inconnu : {kind!r} (attendu deposition ou etch)")
    return StepPreset(name=entry["name"], payload=payload, notes=entry.get("notes"), created_at="preset")


def builtin_step_presets() -> dict[str, StepPreset]:
    """Fallback preset set when ``presets.yml`` is missing - a nitride/semiconductor-
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
