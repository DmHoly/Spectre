"""La gestion de PRISM, réservée aux administrateurs : une page à menu latéral (comme les Paramètres),
une section par sujet - pour l'instant le catalogue des données de caractérisation (les hooks PRISM,
leurs colonnes, un testeur en direct). Les données elles-mêmes viennent de
:mod:`spectre.plugins.characterization` ; ce plugin n'en est que la vitrine d'administration. Dans la
barre du haut, il range son entrée dans le menu « Data », à côté des plaques."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import page_router

# Une base de données (24x24, à trait), devant « PRISM » dans le menu Data.
DATABASE_GLYPH = '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'

PLUGIN = Plugin(
    name="prism",
    depends_on=("accounts", "settings", "characterization"),
    page_router=page_router,  # /prism -> sa première section, et l'ancien /donnees
    pages=(
        Page("/prism/donnees", "prism-data.html"),
        Page("/prism/donnees/{key}", "prism-data.html"),
    ),
    nav=(NavEntry("PRISM", "/prism/donnees", order=40, match=r"^/prism", admin=True, group="data", glyph=DATABASE_GLYPH),),
    title="PRISM",
    description="La gestion de PRISM pour les administrateurs : catalogue des données de caractérisation, colonnes et requêtes de test.",
    icon="database",
)
