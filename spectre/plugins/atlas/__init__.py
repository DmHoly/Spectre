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
            glyph='<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8.5 6h7"/><path d="m7.3 8.2 3.4 7.6"/><path d="m16.7 8.2-3.4 7.6"/>',
            pages=("/management/{slug}", "/management/{slug}/thematiques/{thematique_slug}"),
        ),
    ),
    title="Atlas",
    description="La vue graphe d'un projet corporate : µprojets, études et liens.",
    icon="network",
)
