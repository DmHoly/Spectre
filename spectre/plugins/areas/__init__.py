"""Projets corporate (*management areas*), leurs thématiques et leurs objectifs, et l'équipe à
laquelle chacun appartient : la règle d'écriture ``service.can_manage``."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="areas",
    depends_on=("accounts", "teams"),
    router=router,
    pages=(
        Page("/", "home.html"),
        Page("/management/{slug}", "area.html"),
        Page("/management/{slug}/thematiques/{thematique_slug}", "thematic.html"),
    ),
    nav=(NavEntry("Projets", "/", order=10, match=r"^/(management|microprojets|$)"),),
    migrations=MIGRATIONS,
)
