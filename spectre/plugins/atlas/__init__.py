"""Vue graphe d'un projet corporate : les µprojets dont on est membre, leurs pistes et leurs liens."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="atlas",
    depends_on=("areas", "microprojects", "experiments", "links"),
    router=router,
    pages=(Page("/management/{slug}/atlas", "atlas.html"),),
    # le lien « Atlas » du projet, sur sa page et celles de ses thématiques (area.js / thematic.js en posent l'adresse)
    nav=(
        NavEntry(
            "Atlas",
            "#",
            order=15,
            id="atlas-link",
            pages=("/management/{slug}", "/management/{slug}/thematiques/{thematique_slug}"),
        ),
    ),
)
