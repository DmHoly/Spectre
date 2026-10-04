"""Recherche de la barre du haut : ``GET /api/search``, qui agrège les fournisseurs déclarés par les
autres plugins (``service.register_provider``) - µprojets, plaques, FDL, lots."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="search", depends_on=("accounts",), router=router)
