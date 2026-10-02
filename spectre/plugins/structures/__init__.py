"""Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG et types
de structure (``kinds``). Pages du constructeur."""

from ...kernel.plugin import Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="structures",
    depends_on=("accounts", "library", "attachments"),
    router=router,
    pages=(
        Page("/microprojets/{slug}/briques-technologiques/bibliotheque/nouvelle", "structure-builder.html"),
        Page("/microprojets/{slug}/briques-technologiques/bibliotheque/{name}", "structure-builder.html"),
        Page("/microprojets/{slug}/structures/bibliotheque/nouvelle", "structure-builder.html"),
        Page("/microprojets/{slug}/structures/bibliotheque/{name}", "structure-builder.html"),
        Page("/microprojets/{slug}/structures/nouvelle", "structure-builder.html"),
        Page("/microprojets/{slug}/structures/image", "structure-image.html"),
        Page("/microprojets/{slug}/experiences/{experience_id}/evoluer", "structure-builder.html"),
        Page("/microprojets/{slug}/experiences/{experience_id}/evoluer-image", "structure-image.html"),
    ),
)
