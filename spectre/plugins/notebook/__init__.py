"""Cahier de données d'une étude : instantanés de données de caractérisation et vues DataViz."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="notebook", depends_on=("characterization", "experiments"), router=router)
