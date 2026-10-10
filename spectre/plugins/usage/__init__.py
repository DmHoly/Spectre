"""Mesure de l'utilisation de Spectre, pour les administrateurs : chaque requête d'un compte connecté
est comptée (le compte, l'heure, le module et la route - rien d'autre), et la page Paramètres >
Utilisation en tire l'adoption, les modules utilisés, les pages et les actions, le rythme de
chacun. Désactivé, il ne compte plus rien ; ce qu'il a compté reste."""

from ...kernel.plugin import Page, Plugin
from .api import router
from .migrations import MIGRATIONS
from .recorder import observe

PLUGIN = Plugin(
    name="usage",
    depends_on=("accounts", "settings", "teams"),
    router=router,
    pages=(Page("/parametres/utilisation", "usage.html"),),
    migrations=MIGRATIONS,
    observe=observe,
    title="Utilisation",
    description="Mesure l'usage de l'application : adoption, modules et pages utilisés, par qui et à quel rythme - un tableau de bord réservé aux administrateurs.",
    icon="activity",
)
