"""Bibliothèque racine YAML de l'instance (matériaux, recettes, présets, briques, textes d'UI) et
son éditeur, réservé à l'administrateur."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="library", depends_on=("accounts",), router=router)
