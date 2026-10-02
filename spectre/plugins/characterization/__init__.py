"""Types de données de caractérisation (PRISM, ou démo) : catalogue, requêtes, graphiques
documentaires."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="characterization",
    depends_on=("accounts",),
    router=router,
    pages=(Page("/donnees", "donnees.html"), Page("/donnees/{key}", "donnees.html")),
    nav=(NavEntry("Data", "/donnees", order=40, match=r"^/donnees"),),
)
