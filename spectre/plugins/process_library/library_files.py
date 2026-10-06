"""Les fichiers de la bibliothèque racine que possède ce plugin (``presets.yml``, ``briques.yml`` :
les éléments intégrés), déclarés au registre de ``library`` avec leur interprétation et leur repli."""

from __future__ import annotations

from ..library.service import LibraryFile, parse_entries, register_library_file
from .step_presets import builtin_step_presets, step_preset_from_entry
from .tech_bricks import builtin_tech_bricks, tech_brick_from_entry

register_library_file(
    LibraryFile(
        key="step-presets",
        filename="presets.yml",
        title="Présets d'étape",
        description="Étapes entières déjà réglées (gravure sélective, croissance, nettoyage...), insérées d'un clic depuis la palette du constructeur.",
        parse=lambda data: {p.name: p for p in parse_entries(data, "presets", step_preset_from_entry)},
        fallback=builtin_step_presets,
        order=30,
    )
)
register_library_file(
    LibraryFile(
        key="tech-bricks",
        filename="briques.yml",
        title="Briques technologiques",
        description="Séquences d'étapes réutilisables (masque + gravure, empilement de croissance...) insérables d'un bloc.",
        parse=lambda data: {b.name: b for b in parse_entries(data, "bricks", tech_brick_from_entry)},
        fallback=builtin_tech_bricks,
        order=40,
    )
)
