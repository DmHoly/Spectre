"""Les KPI qu'un µprojet suit : pour chaque µprojet, le choix des KPI (des colonnes de KPI des types de
données PRISM) parmi ceux que PRISM propose, et un onglet qui trace, pour chaque KPI choisi, une boîte à
moustaches par plaque suivie par ses études - calculé à la demande sur les vraies données.
Page ``/microprojets/{slug}/kpi`` : onglet « Distributions » et onglet « Configuration » ; page ``/kpi`` (menu Data) : la configuration de n'importe quel µprojet."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

# Un curseur de réglage (24x24, à trait), devant « KPI » dans le menu Data.
SLIDERS_GLYPH = '<path d="M4 7h10"/><path d="M18 7h2"/><circle cx="16" cy="7" r="2"/><path d="M4 17h2"/><path d="M10 17h10"/><circle cx="8" cy="17" r="2"/>'

PLUGIN = Plugin(
    name="kpi_tracking",
    depends_on=("accounts", "microprojects", "experiments", "characterization"),
    router=router,
    pages=(Page("/kpi", "kpi-config.html"), Page("/microprojets/{slug}/kpi", "kpi-tracking.html")),
    nav=(NavEntry("KPI", "/kpi", order=42, match=r"^/kpi", group="data", glyph=SLIDERS_GLYPH),),
    migrations=MIGRATIONS,
    title="KPI suivis",
    description="Choisit les KPI PRISM qu'un µprojet suit et trace, pour chacun, une boîte à moustaches par plaque suivie par ses études.",
    icon="trend",
)
