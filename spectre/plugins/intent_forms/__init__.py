"""Formulaires d'intention (bibliothèques partagée et par µprojet) et formulaire actif d'un µprojet."""

from ...kernel.plugin import Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="intent_forms",
    depends_on=("experiments", "microprojects"),
    router=router,
    pages=(Page("/microprojets/{slug}/formulaire-intention", "intent-forms.html"),),
)
