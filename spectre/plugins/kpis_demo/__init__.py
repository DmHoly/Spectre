"""Séries et fiche d'étude fictives d'un KPI dont la source réelle n'est pas encore branchée.
Actif seulement si ``SPECTRE_DEMO_DATA=1``."""

from ...kernel.plugin import Plugin
from .api import router
from .service import enabled

PLUGIN = Plugin(
    name="kpis_demo",
    depends_on=("kpis", "structures"),
    router=router,
    enabled=enabled,
)
