"""Saved, reusable structures: a substrate + step list, named and persisted independently of any
experiment - so a structure can be built once (e.g. an epitaxial stack) and reused, or derived
into a new one (e.g. the same stack with contacts added on top, saved under a new name), without
that being tied to launching a particular experience. Two stores per Spectre instance: one shared
across every project, one private to a single project - see :func:`spectre.core.projects.
get_shared_structure_store`/``get_structure_store``. Deliberately not a Follow repository: saved
structures have no lifecycle of their own (no conclusion, no evidence) - they are just a named,
overwritable snapshot a new experience starts from, similar in spirit to ``RecipeStore``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
from structureforge.process.steps import ProcessStep

from .structures import SubstrateSpec


class SavedStructure(BaseModel):
    name: str
    substrate: SubstrateSpec
    steps: list[ProcessStep]
    derived_from: str | None = None
    created_at: str


class StructureLibrary(BaseModel):
    structures: dict[str, SavedStructure] = Field(default_factory=dict)


class StructureLibraryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> StructureLibrary:
        if not self.path.exists():
            return StructureLibrary()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return StructureLibrary.model_validate(data)

    def save(self, library: StructureLibrary) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(library.model_dump_json(indent=2), encoding="utf-8")

    def upsert(self, structure: SavedStructure) -> StructureLibrary:
        library = self.load()
        library.structures[structure.name] = structure
        self.save(library)
        return library

    def rename(self, old_name: str, structure: SavedStructure) -> StructureLibrary:
        """Replace whatever is saved under ``old_name`` with ``structure`` - used when editing a
        saved structure in place also changes its name, so the old key doesn't linger.
        """
        library = self.load()
        library.structures.pop(old_name, None)
        library.structures[structure.name] = structure
        self.save(library)
        return library

    def remove(self, name: str) -> StructureLibrary:
        library = self.load()
        library.structures.pop(name, None)
        self.save(library)
        return library
