"""Les KPI qu'un projet corporate suit : le choix, par projet, de colonnes de KPI des types de données PRISM
(page ``/kpi`` du menu Data), et un onglet par KPI choisi dans le bloc « Évolution des KPI » de la page du
projet, qui trace une boîte à moustaches par plaque - celles de tous les µprojets du projet, calculées à la
demande sur les vraies données."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

# Un curseur de réglage (24x24, à trait), devant « KPI » dans le menu Data.
SLIDERS_GLYPH = '<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/><path d="M4 17h2"/><path d="M10 17h10"/><circle cx="8" cy="17" r="2"/>'

PLUGIN = Plugin(
    name="kpi_tracking",
    depends_on=("accounts", "areas", "microprojects", "experiments", "characterization"),
    router=router,
    pages=(Page("/kpi", "kpi-config.html"),),
    nav=(NavEntry("KPI", "/kpi", order=42, match=r"^/kpi", group="data", glyph=SLIDERS_GLYPH),),
    migrations=MIGRATIONS,
    title="KPI suivis",
    description="Choisit les KPI PRISM que suit un projet corporate et trace, pour chacun, une boîte à moustaches par plaque de ses µprojets, dans le bloc d'évolution des KPI de sa page.",
    icon="trend",
)
