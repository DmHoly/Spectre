"""Images externes référencées (TEM, scans) : la politique des chemins (racines autorisées, formats
affichables) et le parcours des dossiers. Les images elles-mêmes sont un contenu du cahier (plugin
notebook, qui en dépend)."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="external_images", depends_on=("microprojects",), router=router)
