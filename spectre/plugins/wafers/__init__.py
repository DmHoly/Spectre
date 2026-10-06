"""Index des plaques suivies (clé ``wafer_key``), passeport d'une plaque, recherche par lasermark et
par FDL, politique de visibilité."""

from ...kernel.plugin import Page, Plugin
from . import search_provider  # noqa: F401 - déclare les plaques et les FDL à la recherche
from .api import router

PLUGIN = Plugin(
    name="wafers",
    depends_on=("experiments", "search"),
    router=router,
    pages=(Page("/plaques/{lasermark}", "wafer.html"),),
    title="Plaques",
    description="L'index des plaques suivies, leur passeport et leur recherche par lasermark ou FDL.",
    icon="disc",
    required=True,
)
