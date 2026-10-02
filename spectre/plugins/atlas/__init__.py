"""Vue graphe d'un projet corporate : les µprojets dont on est membre, leurs pistes et leurs liens."""

from ...kernel.plugin import Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="atlas",
    depends_on=("areas", "microprojects", "experiments", "links"),
    router=router,
    pages=(Page("/management/{slug}/atlas", "atlas.html"),),
)
