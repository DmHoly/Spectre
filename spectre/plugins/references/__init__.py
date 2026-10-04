"""Références de structure : des points de départ partagés par toute l'application, versionnés
(MAJEUR.MINEUR calculé), publiés depuis les études des µprojets, et leurs usages."""

from ...kernel.plugin import Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="references",
    depends_on=("experiments", "microprojects", "structures"),
    router=router,
    migrations=MIGRATIONS,
)
