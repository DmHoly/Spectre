"""Saved, reusable structures: a substrate + step list, named and persisted independently of any
experiment - so a structure can be built once (e.g. an epitaxial stack) and reused, or derived
into a new one (e.g. the same stack with contacts added on top, saved under a new name), without
that being tied to launching a particular experience. Two stores per Spectre instance: one shared
across every project, one private to a single project - see :func:`spectre.core.projects.
get_shared_structure_store`/``get_structure_store``. Deliberately not a Follow repository: saved
structures have no lifecycle of their own (no conclusion, no evidence) - they are just a named,
overwritable snapshot a new experience starts from, similar in spirit to :mod:`spectre.core.
step_presets`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from structureforge.core.units import Length
from structureforge.process.steps import Deposition, Etch, FacetedGrowth, Lithography, ProcessStep, ResistStrip

from .keyed_store import KeyedJsonStore
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
    convex mesa growing up instead of a concave notch growing down). Everything but the tip
    itself is ordinary Deposition/Etch/Lithography; the tip is a
    :class:`structureforge.process.steps.FacetedGrowth` (kinetic Wulff growth) with the semi-polar
    rate dominating the c-plane rate, so the two facets close in on a point instead of the pillar
    just growing straight up.
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
            Etch(
                name="Gravure RIE du nanofil",
                recipe="Cl2 ICP-RIE (III-N)",
                depth=Length.nm(60),
            ),
            ResistStrip(name="Retrait résine"),
            FacetedGrowth(
                name="Pointe semipolaire (anti-V-pit)",
                material="GaN",
                thickness=Length.nm(40),
                rate_c=0.3,
                rate_m=0.0,
                rate_sp=0.5,
                semi_polar_angle_deg=30.0,
                seed_materials=["GaN"],
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
    :func:`spectre.core.step_presets.default_step_presets` gives standard step presets - always
    available from every project's structure library, under their own ``"preset"`` scope (see
    :func:`spectre.api.structures.list_saved_structures`), never written to a JSON store.
    """
    return {s.name: s for s in [_nanofil_vpit_inverse_preset()]}


class StructureLibrary(BaseModel):
    structures: dict[str, SavedStructure] = Field(default_factory=dict)


def StructureLibraryStore(path: str | Path) -> KeyedJsonStore[StructureLibrary, SavedStructure]:
    return KeyedJsonStore(path, StructureLibrary, "structures")
