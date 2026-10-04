"""Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import search_provider  # noqa: F401 - déclare les lots à la recherche
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="lots",
    depends_on=("wafers", "areas", "experiments", "search"),
    router=router,
    pages=(Page("/lots", "lots.html"), Page("/lots/{code}", "lot.html")),
    nav=(NavEntry("Lots", "/lots", order=30, match=r"^/lots"),),
    migrations=MIGRATIONS,
)
