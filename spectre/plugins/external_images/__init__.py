"""Galerie d'images externes référencées (TEM, scans) d'une étude."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="external_images", depends_on=("experiments",), router=router)
