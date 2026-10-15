"""Types de données de caractérisation (PRISM, ou démo) : catalogue, requêtes, graphiques
documentaires. La page qui les montre est celle du plugin ``prism`` (``/prism/donnees``)."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(
    name="characterization",
    depends_on=("accounts",),
    router=router,
    title="Caractérisation",
    description="Les données de caractérisation PRISM : catalogue, requêtes et graphiques.",
    icon="chart",
)
