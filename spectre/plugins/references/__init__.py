"""Références de structure : des points de départ partagés par toute l'application, versionnés
(MAJEUR.MINEUR calculé), publiés depuis les études des µprojets, et leurs usages. Pages : la liste
des références et l'évolution d'une référence."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import (
    comparison_source,  # noqa: F401 - déclare les versions de référence au comparateur
)
from .api import router
from .migrations import MIGRATIONS

REFERENCE_GLYPH = '<path d="M6 3h12v18l-6-4-6 4Z"/>'

PLUGIN = Plugin(
    name="references",
    depends_on=("experiments", "microprojects", "structures", "comparator"),
    router=router,
    pages=(Page("/references", "references.html"), Page("/references/{slug}", "reference.html")),
    nav=(NavEntry("Références", "/references", order=25, match=r"^/references", group="structure", glyph=REFERENCE_GLYPH),),
    migrations=MIGRATIONS,
    title="Références de structure",
    description="Les références de toute l'application : versions publiées depuis les études, leur évolution et leurs usages.",
    icon="bookmark",
)
