"""Index des plaques suivies (clé ``wafer_key``), passeport d'une plaque, recherche par lasermark et
par FDL, politique de visibilité ; les plaques que contient une FDL (:mod:`.fdl_source`)."""

from ...kernel.plugin import Page, Plugin
from . import search_provider  # noqa: F401 - déclare les plaques et les FDL à la recherche
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="wafers",
    depends_on=("experiments", "search"),
    router=router,
    migrations=MIGRATIONS,
    pages=(Page("/plaques/{lasermark}", "wafer.html"),),
    title="Plaques",
    description="L'index des plaques suivies, leur passeport, leur recherche par lasermark ou FDL et les plaques de chaque FDL.",
    icon="disc",
    required=True,
)
