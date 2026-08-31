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
from structureforge.core.units import Length
from structureforge.process.steps import Deposition, Etch, Lithography, ProcessStep, ResistStrip, SemipolarFacet

from .structures import SubstrateSpec


class SavedStructure(BaseModel):
    name: str
    substrate: SubstrateSpec
    steps: list[ProcessStep]
    derived_from: str | None = None
    created_at: str


def _nanofil_vpit_inverse_preset() -> SavedStructure:
    """A selective-area-grown GaN nanowire tapering to a facetted point on two symmetric
    semipolar planes - an "anti-V-pit" (the same {1-101}-type facets a V-pit shows, but on a
    convex mesa growing up instead of a concave notch growing down), the shape
    ``structureforge/examples/nanowire_semipolar_tip.py`` demonstrates. Everything but the facet
    itself is ordinary Deposition/Etch/Lithography; the facet is a
    :class:`structureforge.process.steps.SemipolarFacet`, the one shape those recipes can't
    reproduce on their own (see its docstring).
    """
    domain_width_nm = 300.0
    cx = domain_width_nm / 2
    pillar_half_width_nm = 30.0
    return SavedStructure(
        name="Nanofil pointe semipolaire (V-pit inversé)",
        substrate=SubstrateSpec(material="Sapphire", domain_width=Length.nm(domain_width_nm), thickness=Length.nm(20)),
        steps=[
            Deposition(name="Tampon AlN", material="AlN", recipe="MOCVD Epitaxial", thickness=Length.nm(10)),
            Deposition(name="GaN (précurseur)", material="GaN", recipe="MOCVD Epitaxial", thickness=Length.nm(60)),
            Lithography(
                name="Masque du nanofil",
                resist_material="Photoresist",
                thickness=Length.nm(80),
                openings=[(0.0, cx - pillar_half_width_nm), (cx + pillar_half_width_nm, domain_width_nm)],
            ),
            Etch(name="Gravure RIE du nanofil", recipe="Cl2 ICP-RIE (III-N)", depth=Length.nm(60)),
            ResistStrip(name="Retrait résine"),
            SemipolarFacet(
                name="Pointe semipolaire (anti-V-pit)",
                orientation="tip",
                base_half_width=Length.nm(pillar_half_width_nm),
                tip_half_width=Length.nm(8),
                facet_angle_deg=60.0,
            ),
            Deposition(name="Puits quantique InGaN", material="InGaN", recipe="MOCVD Epitaxial", thickness=Length.nm(3)),
            Deposition(name="Capot GaN", material="GaN", recipe="MOCVD Epitaxial", thickness=Length.nm(8)),
            Deposition(name="Contact ITO", material="ITO", recipe="Sputter Metal (normal)", thickness=Length.nm(15)),
        ],
        derived_from=None,
        created_at="preset",
    )


def default_structure_presets() -> dict[str, SavedStructure]:
    """Built-in structure presets, the same "standard, not stored, not deletable" status
    ``structureforge.core.recipes.default_recipes()`` gives standard recipes - always available
    from every project's structure library, under their own ``"preset"`` scope (see
    :func:`spectre.api.structures.list_saved_structures`), never written to a JSON store.
    """
    return {s.name: s for s in [_nanofil_vpit_inverse_preset()]}


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
