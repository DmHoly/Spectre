"""Planning d'équipe : les plaques des études d'une équipe par thématique ▸ µprojet ▸ épi, leurs
lots en cours et prévus, sur une frise par semaine."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="planning",
    depends_on=("teams", "areas", "microprojects", "structures", "experiments", "wafers", "lots"),
    router=router,
    pages=(Page("/planning", "planning.html"), Page("/planning/{team_slug}", "planning.html")),
    nav=(NavEntry("Planning", "/planning", order=32, match=r"^/planning"),),
    title="Planning d'équipe",
    description="Pour les managers : les plaques de l'équipe par thématique et µprojet, leurs lots en cours et les lots prévus.",
    icon="calendar",
)
