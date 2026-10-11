"""Équipes et leurs membres (manager ou membre). Ce qu'une équipe possède - ses projets corporate,
donc leurs µprojets - est dit par les plugins au-dessus (``areas``)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

TEAMS_GLYPH = '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M21.5 20a6.5 6.5 0 0 0-4-6"/>'

PLUGIN = Plugin(
    name="teams",
    depends_on=("accounts",),
    router=router,
    pages=(Page("/equipes", "teams.html"), Page("/equipes/{slug}", "team.html")),
    nav=(NavEntry("Équipes", "/equipes", order=45, match=r"^/equipes", group="gestion", glyph=TEAMS_GLYPH),),
    migrations=MIGRATIONS,
    title="Équipes",
    description="Les équipes, leurs managers et leurs membres : qui gère quels projets corporate.",
    icon="users",
)
