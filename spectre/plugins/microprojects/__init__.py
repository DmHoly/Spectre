"""µprojets (numéro, rattachement à un projet ou une thématique, recherche), membres, rôles et
invitations. Fournit ``deps.require_role``."""

from ...kernel.plugin import Page, Plugin
from . import search_provider  # noqa: F401 - déclare les µprojets à la recherche
from .api import page_router, router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="microprojects",
    depends_on=("accounts", "areas", "search"),
    router=router,
    page_router=page_router,
    pages=(Page("/microprojets/{slug}", "microproject.html"),),
    migrations=MIGRATIONS,
)
