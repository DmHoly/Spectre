"""La fiche data des plaques : un onglet « Data » sur la page d'une plaque rattachée à un µprojet - le récapitulatif
de ses données principales (valeurs situées parmi les plaques du projet, histogrammes, cartographies, courbes,
images) et sa généalogie (les études d'où elle vient et celles qui la reprennent, µprojet par µprojet). Ce que
montre la fiche se configure par projet corporate (page ``/fiche-data`` du menu Data, comme les KPI suivis) ;
ce qu'elle calcule se garde résumé, hors de la base de Spectre (:mod:`.store`)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from ..wafers import timeline
from . import timeline_source
from .api import router
from .migrations import MIGRATIONS

# La frise d'une plaque : les jours où chaque type de données PRISM l'a mesurée.
timeline.register_source("wafer_data", timeline_source.data_events)

# Une fiche à quatre cases (24x24, à trait), devant « Fiche data » dans le menu Data.
SHEET_GLYPH = '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><path d="M14 20l2.5-3 2 2L21 15"/>'

PLUGIN = Plugin(
    name="wafer_data",
    depends_on=("accounts", "areas", "microprojects", "experiments", "wafers", "characterization", "external_images", "kpi_tracking"),
    router=router,
    pages=(Page("/fiche-data", "wafer-data-config.html"),),
    nav=(NavEntry("Fiche data", "/fiche-data", order=43, match=r"^/fiche-data", group="data", glyph=SHEET_GLYPH),),
    migrations=MIGRATIONS,
    title="Fiche data des plaques",
    description="Un onglet « Data » sur la page d'une plaque suivie : ses données principales (valeurs, histogrammes, boîtes, nuages, cartographies, courbes, galeries d'images), aux colonnes typées, configurées par projet corporate, et sa généalogie.",
    icon="chart",
)
