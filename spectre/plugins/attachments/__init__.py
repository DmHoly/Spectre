"""Fichiers téléversés d'un µprojet (blob + sidecar), types, tailles et service des octets."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(name="attachments", depends_on=("microprojects",), router=router)
