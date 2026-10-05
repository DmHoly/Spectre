"""Références de structure : des points de départ partagés par toute l'application, versionnés
(MAJEUR.MINEUR calculé), publiés depuis les études des µprojets, et leurs usages. Pages : la liste
des références et l'évolution d'une référence."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="references",
    depends_on=("experiments", "microprojects", "structures"),
    router=router,
    pages=(Page("/references", "references.html"), Page("/references/{slug}", "reference.html")),
    nav=(NavEntry("Références", "/references", order=25, match=r"^/references"),),
    migrations=MIGRATIONS,
)
