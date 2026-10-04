"""Cahier de données d'une étude : toutes ses données mesurées - instantanés de données de
caractérisation et leurs vues DataViz (entrées PRISM), et ce qui se charge à la main (entrées
manuelles : valeurs, textes, tableaux, fichiers, liens), chacune rattachée aux plaques mesurées et
aux étapes du procédé ; une mesure manuelle référence aussi des images externes (plugin
external_images), servies par identifiant."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="notebook", depends_on=("characterization", "experiments", "attachments", "external_images"), router=router)
