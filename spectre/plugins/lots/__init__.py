"""Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import search_provider  # noqa: F401 - déclare les lots à la recherche
from .api import router
from .migrations import MIGRATIONS

LOTS_GLYPH = '<path d="m12 3 8 4.5v9L12 21l-8-4.5v-9Z"/><path d="m4 7.5 8 4.5 8-4.5"/><path d="M12 12v9"/>'

PLUGIN = Plugin(
    name="lots",
    depends_on=("wafers", "areas", "experiments", "search"),
    router=router,
    pages=(Page("/lots", "lots.html"), Page("/lots/{code}", "lot.html")),
    nav=(NavEntry("Lots", "/lots", order=41, match=r"^/lots", group="data", glyph=LOTS_GLYPH),),
    migrations=MIGRATIONS,
    title="Lots",
    description="Les lots de fabrication, leurs plaques, leurs thématiques visées et le Gantt.",
    icon="calendar",
)
