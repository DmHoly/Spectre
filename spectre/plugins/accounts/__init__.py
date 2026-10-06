"""Comptes, sessions, mot de passe, profil et rôle administrateur global."""

from ...kernel.plugin import Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="accounts",
    router=router,
    pages=(
        Page("/connexion", "login.html"),
        Page("/inscription", "signup.html"),
        Page("/mot-de-passe-oublie", "password-forgot.html"),
        Page("/reinitialiser", "password-reset.html"),
        Page("/profil", "profile.html"),
    ),
    migrations=MIGRATIONS,
    title="Comptes",
    description="Comptes, connexion, mot de passe et profil ; le rôle administrateur.",
    icon="user",
    required=True,
)
