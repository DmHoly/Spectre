"""Bibliothèque racine YAML de l'instance : registre des fichiers déclarés par leurs plugins
propriétaires, chargeur avec cache, éditeur réservé à l'administrateur, textes d'interface."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="library", depends_on=("accounts",), router=router,
    title="Bibliothèque racine",
    description="Les fichiers YAML de l'instance : matériaux, recettes, présets, briques et textes d'interface.",
    icon="book",
)
