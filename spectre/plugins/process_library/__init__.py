"""Structures enregistrées, présets d'étape et briques technologiques (intégrés, partagés, propres
à un µprojet). Pages bibliothèque, présets et briques."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="process_library",
    depends_on=("structures", "microprojects", "library"),
    router=router,
    pages=(
        Page("/bibliotheque", "bibliotheque.html"),
        Page("/microprojets/{slug}/presets-etapes", "presets.html"),
        Page("/microprojets/{slug}/briques-technologiques", "briques.html"),
    ),
    nav=(NavEntry("Bibliothèque", "/bibliotheque", order=20, match=r"^/bibliotheque"),),
)
