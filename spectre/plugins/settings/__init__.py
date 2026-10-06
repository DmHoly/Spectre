"""Paramètres de l'application, réservés aux administrateurs : une page à menu latéral, une section
par couche réglable. Première section : les plugins et leur activation (la règle est au noyau,
``spectre.kernel.plugin_states``)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import page_router, router

PLUGIN = Plugin(
    name="settings",
    depends_on=("accounts",),
    router=router,
    page_router=page_router,  # /parametres -> sa première section
    pages=(Page("/parametres/plugins", "plugins.html"),),
    nav=(NavEntry("Paramètres", "/parametres/plugins", order=90, match=r"^/parametres", admin=True),),
    title="Paramètres",
    description="Les réglages de l'application réservés aux administrateurs, dont cette page.",
    icon="settings",
    required=True,
)
