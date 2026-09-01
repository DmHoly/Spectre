"""Saved, reusable step presets: a preconfigured mode/angle/selectivity for a deposition or an
etch, named and persisted independently of any structure - so instead of filling in "conforme",
"directionnel, 0deg, sélectif au photorésist..." by hand on every single etch step, you pick a
preset once. This is exactly the role recipes used to play in StructureForge itself (the 11
built-in presets below carry the same names, physics and French descriptions the old standard
recipes had - see :mod:`structureforge.core.recipes`) - moved up to Spectre now that StructureForge
steps carry their own mode/angle/selectivity directly and no longer resolve a recipe by name.

Two stores per Spectre instance, the same split as :mod:`spectre.core.structure_library`: one
shared across every project, one private to a single project - see :func:`spectre.core.projects.
get_shared_step_preset_store`/``get_step_preset_store``. Applying a preset only pre-fills a step's
form fields client-side (see ``structure-builder.js``); once added, a step carries its own
mode/angle/selectivity independently, the same "point of departure, not a live link" relationship
the structure library already has between a preset structure and the experience derived from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field
from structureforge.core.materials import MaterialCategory
from structureforge.core.recipes import DepositionMode, EtchMode


class DepositionPreset(BaseModel):
    kind: Literal["deposition"] = "deposition"
    mode: DepositionMode
    angle_deg: float = 0.0


class EtchPreset(BaseModel):
    kind: Literal["etch"] = "etch"
    mode: EtchMode
    angle_deg: float = 0.0
    selectivity_by_material: dict[str, float] = Field(default_factory=dict)
    selectivity_by_category: dict[MaterialCategory, float] = Field(default_factory=dict)
    default_factor: float = 1.0


StepPresetPayload = Annotated[Union[DepositionPreset, EtchPreset], Field(discriminator="kind")]


class StepPreset(BaseModel):
    name: str
    payload: StepPresetPayload
    notes: str | None = None
    created_at: str


class StepPresetLibrary(BaseModel):
    presets: dict[str, StepPreset] = Field(default_factory=dict)


class StepPresetStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> StepPresetLibrary:
        if not self.path.exists():
            return StepPresetLibrary()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return StepPresetLibrary.model_validate(data)

    def save(self, library: StepPresetLibrary) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(library.model_dump_json(indent=2), encoding="utf-8")

    def upsert(self, preset: StepPreset) -> StepPresetLibrary:
        library = self.load()
        library.presets[preset.name] = preset
        self.save(library)
        return library

    def rename(self, old_name: str, preset: StepPreset) -> StepPresetLibrary:
        """Replace whatever is saved under ``old_name`` with ``preset`` - used when editing a
        preset in place also changes its name, so the old key doesn't linger.
        """
        library = self.load()
        library.presets.pop(old_name, None)
        library.presets[preset.name] = preset
        self.save(library)
        return library

    def remove(self, name: str) -> StepPresetLibrary:
        library = self.load()
        library.presets.pop(name, None)
        self.save(library)
        return library


def default_step_presets() -> dict[str, StepPreset]:
    """Built-in presets, the same "standard, not stored, not deletable" status
    ``structureforge.core.recipes`` used to give its own standard recipes - always available from
    every project's preset library, under their own ``"preset"`` scope (see
    :func:`spectre.api.structures.list_step_presets`), never written to a JSON store.
    """
    deposition = [
        StepPreset(
            name="ALD Conformal",
            payload=DepositionPreset(mode=DepositionMode.conformal),
            notes="Dépôt uniforme qui épouse parfaitement tous les reliefs de la surface.",
            created_at="preset",
        ),
        StepPreset(
            name="CVD Conformal",
            payload=DepositionPreset(mode=DepositionMode.conformal),
            notes="Dépôt uniforme sur les reliefs, une bonne couverture standard.",
            created_at="preset",
        ),
        StepPreset(
            name="PVD Sputter (tilted)",
            payload=DepositionPreset(mode=DepositionMode.directional, angle_deg=15.0),
            notes="Dépôt métallique en visée directe, légèrement incliné — les zones cachées sont moins couvertes.",
            created_at="preset",
        ),
        StepPreset(
            name="Evaporation (normal)",
            payload=DepositionPreset(mode=DepositionMode.directional, angle_deg=0.0),
            notes="Dépôt métallique tout droit par le dessus — ne couvre presque pas les flancs, adapté à un lift-off.",
            created_at="preset",
        ),
        StepPreset(
            name="MOCVD Epitaxial",
            payload=DepositionPreset(mode=DepositionMode.conformal),
            notes="Croissance épitaxiale (semi-conducteurs III-N/III-V) sur une base plane.",
            created_at="preset",
        ),
        StepPreset(
            name="PECVD Conformal",
            payload=DepositionPreset(mode=DepositionMode.conformal),
            notes="Dépôt assisté par plasma, à plus basse température — bonne couverture des reliefs.",
            created_at="preset",
        ),
        StepPreset(
            name="Sputter Metal (normal)",
            payload=DepositionPreset(mode=DepositionMode.directional, angle_deg=0.0),
            notes="Dépôt métallique par pulvérisation, par le dessus — couvre mieux les flancs qu'une évaporation, reste directionnel.",
            created_at="preset",
        ),
        StepPreset(
            name="Electroplating (Cu)",
            payload=DepositionPreset(mode=DepositionMode.conformal),
            notes="Remplissage électrochimique en cuivre — nécessite une couche d'amorce déjà en place.",
            created_at="preset",
        ),
    ]
    etch = [
        StepPreset(
            name="Dry Oxide Etch",
            payload=EtchPreset(
                mode=EtchMode.isotropic,
                selectivity_by_category={MaterialCategory.dielectric: 1.0},
                default_factor=0.8,
            ),
            notes="Gravure sèche qui attaque surtout les oxydes ; grave presque aussi vite tout le reste.",
            created_at="preset",
        ),
        StepPreset(
            name="Wet HF Dip",
            payload=EtchPreset(
                mode=EtchMode.isotropic,
                selectivity_by_category={MaterialCategory.dielectric: 1.0},
                default_factor=0.05,
            ),
            notes="Bain humide très sélectif de l'oxyde — épargne le nitrure, le silicium et les métaux.",
            created_at="preset",
        ),
        StepPreset(
            name="Anisotropic RIE",
            payload=EtchPreset(
                mode=EtchMode.directional,
                angle_deg=0.0,
                selectivity_by_material={"Photoresist": 0.1},
                default_factor=1.0,
            ),
            notes="Gravure sèche quasi verticale — le masque de résine s'érode lentement, tout le reste au rythme normal.",
            created_at="preset",
        ),
        StepPreset(
            name="Ion Mill (tilted)",
            payload=EtchPreset(mode=EtchMode.directional, angle_deg=30.0, default_factor=1.0),
            notes="Gravure physique inclinée (usinage ionique) — attaque presque tous les matériaux au même rythme.",
            created_at="preset",
        ),
        StepPreset(
            name="KOH Anisotropic Wet Etch",
            payload=EtchPreset(
                mode=EtchMode.directional,
                angle_deg=54.7,
                selectivity_by_material={"Si": 1.0},
                default_factor=0.02,
            ),
            notes="Gravure humide cristallographique du silicium, angle fixe à 54,7° — s'arrête presque totalement sur un masque oxyde/nitrure.",
            created_at="preset",
        ),
        StepPreset(
            name="Cl2 ICP-RIE (III-N)",
            payload=EtchPreset(
                mode=EtchMode.directional,
                angle_deg=0.0,
                selectivity_by_material={"GaN": 1.0, "AlGaN": 1.0, "InGaN": 1.0, "AlN": 1.0},
                default_factor=0.05,
            ),
            notes="Gravure sèche quasi verticale des semi-conducteurs III-N (GaN, AlGaN...) — sélective par rapport aux masques, diélectriques et métaux.",
            created_at="preset",
        ),
        StepPreset(
            name="TMAH Anisotropic Wet Etch",
            payload=EtchPreset(
                mode=EtchMode.directional,
                angle_deg=54.7,
                selectivity_by_material={"Si": 1.0},
                default_factor=0.02,
            ),
            notes="Alternative au KOH sans contamination alcaline, même angle cristallographique — plus douce sur l'aluminium exposé.",
            created_at="preset",
        ),
        StepPreset(
            name="SF6 Deep RIE (Si)",
            payload=EtchPreset(
                mode=EtchMode.directional,
                angle_deg=0.0,
                selectivity_by_material={"Si": 1.0, "SiO2": 0.02, "Si3N4": 0.02, "Photoresist": 0.05},
                default_factor=1.0,
            ),
            notes="Gravure profonde du silicium (type Bosch) — quasi verticale et rapide, s'arrête bien sur un masque oxyde/nitrure/résine.",
            created_at="preset",
        ),
        StepPreset(
            name="Wet Metal Etch",
            payload=EtchPreset(
                mode=EtchMode.isotropic,
                selectivity_by_category={MaterialCategory.metal: 1.0},
                default_factor=0.05,
            ),
            notes="Bain humide générique pour graver un métal — attaque lentement tout le reste ; sous-grave comme toute gravure isotrope.",
            created_at="preset",
        ),
    ]
    return {p.name: p for p in [*deposition, *etch]}
