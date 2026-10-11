"""Types de données de caractérisation (PRISM, ou démo) : catalogue, requêtes, graphiques
documentaires."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

DATA_GLYPH = '<path d="M3 3v18h18"/><path d="m7 15 4-5 3 3 5-6"/>'

PLUGIN = Plugin(
    name="characterization",
    depends_on=("accounts",),
    router=router,
    pages=(Page("/donnees", "data-types.html"), Page("/donnees/{key}", "data-types.html")),
    nav=(NavEntry("Data", "/donnees", order=40, match=r"^/donnees", glyph=DATA_GLYPH),),
    title="Caractérisation",
    description="Les données de caractérisation PRISM : catalogue, requêtes et graphiques.",
    icon="chart",
)
