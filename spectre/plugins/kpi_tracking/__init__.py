"""Les KPI qu'un µprojet suit : pour chaque µprojet, le choix des KPI (des colonnes de KPI des types de
données PRISM) parmi ceux que PRISM propose, et un onglet qui trace, pour chaque KPI choisi, une boîte à
moustaches par plaque suivie par ses études - calculé à la demande sur les vraies données.
Page ``/microprojets/{slug}/kpi`` : onglet « Distributions » et onglet « Configuration »."""

from ...kernel.plugin import Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="kpi_tracking",
    depends_on=("accounts", "microprojects", "experiments", "characterization"),
    router=router,
    pages=(Page("/microprojets/{slug}/kpi", "kpi-tracking.html"),),
    migrations=MIGRATIONS,
    title="KPI suivis",
    description="Choisit les KPI PRISM qu'un µprojet suit et trace, pour chacun, une boîte à moustaches par plaque suivie par ses études.",
    icon="trend",
)
