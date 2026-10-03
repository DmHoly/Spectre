"""Recherche de la barre du haut : µprojets, lots, plaques et FDL. Pour l'instant le front seul
(``static/topbar-search.js``), qui interroge les recherches de microprojects, wafers et lots ;
``GET /api/search`` et ses fournisseurs viendront avec le passage REST (``ARCHITECTURE.md`` § 5)."""

from ...kernel.plugin import Plugin

PLUGIN = Plugin(name="search", depends_on=("accounts",))
