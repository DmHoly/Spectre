"""Liens entre µprojets et entre entités physiques."""

from ...kernel.plugin import Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(name="links", depends_on=("microprojects", "experiments"), router=router, migrations=MIGRATIONS)
