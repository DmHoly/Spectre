"""Paramètres de l'application, réservés aux administrateurs : une page à menu latéral, une section
par couche réglable - les plugins et leur activation (``spectre.kernel.plugin_states``), la base de
données : sauvegarde en ZIP et exploration de ses tables (``spectre.kernel.database``)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import page_router, router

# Une roue crantée (24x24, à trait), à côté de la session dans la barre du haut.
GEAR_ICON = (
    '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 '
    "1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 "
    "1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 "
    "2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 "
    "1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z\"/>"
)

PLUGIN = Plugin(
    name="settings",
    depends_on=("accounts",),
    router=router,
    page_router=page_router,  # /parametres -> sa première section
    pages=(
        Page("/parametres/plugins", "plugins.html"),
        Page("/parametres/base-de-donnees", "database.html"),
    ),
    nav=(NavEntry("Paramètres", "/parametres/plugins", order=90, match=r"^/parametres", admin=True, icon=GEAR_ICON),),
    title="Paramètres",
    description="Les réglages de l'application réservés aux administrateurs : plugins, base de données.",
    icon="settings",
    required=True,
)
