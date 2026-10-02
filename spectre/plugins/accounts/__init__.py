"""Comptes, sessions, mot de passe, profil et rôle administrateur global."""

from ...kernel.plugin import Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="accounts",
    router=router,
    pages=(
        Page("/connexion", "connexion.html"),
        Page("/inscription", "inscription.html"),
        Page("/mot-de-passe-oublie", "mot-de-passe-oublie.html"),
        Page("/reinitialiser", "reinitialiser.html"),
        Page("/profil", "profil.html"),
    ),
    migrations=MIGRATIONS,
)
