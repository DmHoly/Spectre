"""Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG et types
de structure (``kinds``). Pages du constructeur."""

from ...kernel.plugin import Page, Plugin
from . import library_files  # noqa: F401 - déclare materiaux.yml et recettes.yml à la bibliothèque
from .api import router

PLUGIN = Plugin(
    name="structures",
    depends_on=("accounts", "library", "attachments"),
    router=router,
    pages=(
        Page("/microprojets/{slug}/briques-technologiques/bibliotheque/nouvelle", "builder.html"),
        Page("/microprojets/{slug}/briques-technologiques/bibliotheque/{brick_id}", "builder.html"),
        Page("/microprojets/{slug}/presets-etapes/bibliotheque/nouvelle", "builder.html"),
        Page("/microprojets/{slug}/presets-etapes/bibliotheque/{preset_id}", "builder.html"),
        Page("/microprojets/{slug}/structures/bibliotheque/nouvelle", "builder.html"),
        Page("/microprojets/{slug}/structures/bibliotheque/{structure_id}", "builder.html"),
        Page("/microprojets/{slug}/structures/nouvelle", "builder.html"),
        Page("/microprojets/{slug}/structures/image", "image-structure.html"),
        Page("/microprojets/{slug}/experiences/{experiment_id}/evoluer", "builder.html"),
        Page("/microprojets/{slug}/experiences/{experiment_id}/evoluer-image", "image-structure.html"),
    ),
    title="Structures",
    description="Le constructeur : matériaux, recettes, simulation StructureForge, campagnes DOE et rendu des structures.",
    icon="layers",
)
