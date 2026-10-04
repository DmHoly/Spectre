"""Équipes et leurs membres (manager ou membre). Ce qu'une équipe possède - ses projets corporate,
donc leurs µprojets - est dit par les plugins au-dessus (``areas``)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="teams",
    depends_on=("accounts",),
    router=router,
    pages=(Page("/equipes", "teams.html"), Page("/equipes/{slug}", "team.html")),
    nav=(NavEntry("Équipes", "/equipes", order=45, match=r"^/equipes"),),
    migrations=MIGRATIONS,
)
