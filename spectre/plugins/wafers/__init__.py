"""Index des plaques suivies (clé ``wafer_key``) et sa page ``/plaques`` - la liste et sa recherche -,
passeport d'une plaque, recherche par lasermark et par FDL, politique de visibilité ; les plaques
que contient une FDL (:mod:`.fdl_source`)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import search_provider  # noqa: F401 - déclare les plaques et les FDL à la recherche
from . import comparison_source  # noqa: F401 - déclare les plaques au comparateur
from .api import router
from .migrations import MIGRATIONS

# Une plaque (24x24, à trait), devant « Plaques » dans le menu Data.
DISC_GLYPH = '<circle cx="12" cy="12" r="9"/><path d="M12 3v3"/><circle cx="12" cy="12" r="2"/>'

PLUGIN = Plugin(
    name="wafers",
    depends_on=("experiments", "search", "comparator"),
    router=router,
    migrations=MIGRATIONS,
    pages=(Page("/plaques", "wafer-index.html"), Page("/plaques/{lasermark}", "wafer.html")),
    nav=(NavEntry("Plaques", "/plaques", order=41, match=r"^/plaques", group="data", glyph=DISC_GLYPH),),
    title="Plaques",
    description="L'index des plaques suivies, leur passeport, leur recherche par lasermark ou FDL et les plaques de chaque FDL.",
    icon="disc",
    required=True,
)
