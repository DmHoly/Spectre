"""Structures enregistrées, présets d'étape et briques technologiques (intégrés, partagés, propres
à un µprojet). Pages bibliothèque, présets et briques."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import library_files  # noqa: F401 - déclare presets.yml et briques.yml à la bibliothèque
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="process_library",
    depends_on=("structures", "microprojects", "library"),
    router=router,
    pages=(
        Page("/bibliotheque", "library-hub.html"),
        Page("/microprojets/{slug}/presets-etapes", "step-presets.html"),
        Page("/microprojets/{slug}/briques-technologiques", "tech-bricks.html"),
    ),
    nav=(NavEntry("Bibliothèque", "/bibliotheque", order=20, match=r"^/bibliotheque"),),
    migrations=MIGRATIONS,
)
