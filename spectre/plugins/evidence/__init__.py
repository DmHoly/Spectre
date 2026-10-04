"""Preuves d'une étude : liens, mesures, images et leurs annotations."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="evidence", depends_on=("experiments", "attachments"), router=router)
