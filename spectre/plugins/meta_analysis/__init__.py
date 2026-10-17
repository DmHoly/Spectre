"""Méta-analyse de plaques : une plaque de référence et celles qu'on lui compare, d'une étude ou d'une
autre, sur une même fiche - leurs structures côte à côte, le tableau du comparateur, le contexte de chacune
(ses études, ses notes, qu'on enrichit d'ici) et la conclusion de l'analyse. Pages ``/analyses`` et
``/analyses/{id}`` ; la page d'une plaque liste les analyses où elle paraît."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

# Deux plaques sous une loupe (24x24, à trait), devant « Analyses » dans le menu Data.
LENS_GLYPH = '<circle cx="7" cy="8" r="4"/><circle cx="17" cy="8" r="4"/><circle cx="13" cy="17" r="3.5"/><path d="m15.5 19.5 3 3"/>'

PLUGIN = Plugin(
    name="meta_analysis",
    depends_on=("accounts", "areas", "microprojects", "experiments", "comparator", "wafers", "kpi_tracking"),
    router=router,
    pages=(Page("/analyses", "analyses.html"), Page("/analyses/{analysis_id}", "analysis.html")),
    nav=(NavEntry("Analyses", "/analyses", order=44, match=r"^/analyses", group="data", glyph=LENS_GLYPH),),
    migrations=MIGRATIONS,
    title="Méta-analyse de plaques",
    description="Compare une plaque de référence à d'autres plaques, d'une étude ou d'une autre : structures côte à côte, tableau du comparateur, contexte de chacune et conclusion de l'analyse.",
    icon="compare",
)
