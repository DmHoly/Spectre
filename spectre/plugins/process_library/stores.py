"""Where the three libraries live: one JSON file inside each microproject's own directory, and one
shared file visible from every microproject (see :class:`spectre.kernel.json_store.KeyedJsonStore`).
"""

from __future__ import annotations

from ...kernel.db import data_dir
from ...kernel.json_store import KeyedJsonStore
from ..microprojects.service import microproject_dir
from .step_presets import StepPresetStore
from .structure_library import StructureLibraryStore
from .tech_bricks import TechBrickStore


def get_structure_store(slug: str) -> KeyedJsonStore:
    return StructureLibraryStore(microproject_dir(slug) / "structures.json")


def get_shared_structure_store() -> KeyedJsonStore:
    return StructureLibraryStore(data_dir() / "structures_partagees.json")


def get_step_preset_store(slug: str) -> KeyedJsonStore:
    return StepPresetStore(microproject_dir(slug) / "presets_etapes.json")


def get_shared_step_preset_store() -> KeyedJsonStore:
    return StepPresetStore(data_dir() / "presets_etapes_partages.json")


def get_tech_brick_store(slug: str) -> KeyedJsonStore:
    return TechBrickStore(microproject_dir(slug) / "briques.json")


def get_shared_tech_brick_store() -> KeyedJsonStore:
    return TechBrickStore(data_dir() / "briques_partagees.json")
