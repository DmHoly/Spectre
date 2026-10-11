"""Planning d'équipe : les plaques des études d'une équipe par thématique ▸ µprojet ▸ épi, leurs
lots en cours et prévus, sur une frise par semaine."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

PLANNING_GLYPH = '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4"/><path d="M16 2v4"/><path d="M3 10h18"/>'

PLUGIN = Plugin(
    name="planning",
    depends_on=("teams", "areas", "microprojects", "structures", "experiments", "wafers", "lots"),
    router=router,
    pages=(Page("/planning", "planning.html"), Page("/planning/{team_slug}", "planning.html")),
    nav=(NavEntry("Planning", "/planning", order=32, match=r"^/planning", group="gestion", glyph=PLANNING_GLYPH),),
    title="Planning d'équipe",
    description="Pour les managers : les plaques de l'équipe par thématique et µprojet, leurs lots en cours et les lots prévus.",
    icon="calendar",
)
