"""Séries et fiche d'étude fictives d'un KPI dont la source réelle n'est pas encore branchée."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(
    name="kpis_demo",
    depends_on=("kpis", "structures"),
    router=router,
    enabled=lambda: True,
)
