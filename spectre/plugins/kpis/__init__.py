"""Registre des KPI (``service.register``) et séries mensuelles d'un projet corporate."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="kpis", depends_on=("areas", "experiments"), router=router)
