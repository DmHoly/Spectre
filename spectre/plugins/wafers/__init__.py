"""Index des plaques suivies, recherche par lasermark et par FDL, passeport d'une plaque."""

from ...kernel.plugin import Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="wafers",
    depends_on=("experiments", "search"),
    router=router,
    pages=(Page("/plaques/{lasermark}", "wafer.html"),),
)
