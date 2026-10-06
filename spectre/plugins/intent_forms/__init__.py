"""Formulaires d'intention (bibliothèques partagée et par µprojet) et formulaire actif d'un µprojet."""

from ...kernel.plugin import Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="intent_forms",
    depends_on=("experiments", "microprojects"),
    router=router,
    pages=(Page("/microprojets/{slug}/formulaire-intention", "intent-forms.html"),),
    migrations=MIGRATIONS,
    title="Formulaires d'intention",
    description="Les questions posées au lancement d'une étude, choisies par µprojet.",
    icon="clipboard",
)
