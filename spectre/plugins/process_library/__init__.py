"""Structures enregistrées, présets d'étape et briques technologiques (intégrés, partagés, propres
à un µprojet). Pages bibliothèque, présets et briques."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import library_files  # noqa: F401 - déclare presets.yml et briques.yml à la bibliothèque
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="process_library",
    # experiments : où servent les briques (usages.py, les études qui en ont une copie)
    depends_on=("structures", "microprojects", "library", "experiments"),
    router=router,
    pages=(
        Page("/bibliotheque", "library-hub.html"),
        Page("/microprojets/{slug}/presets-etapes", "step-presets.html"),
        Page("/microprojets/{slug}/briques-technologiques", "tech-bricks.html"),
        Page("/microprojets/{slug}/macro-etapes", "macro-steps.html"),
    ),
    nav=(NavEntry("Bibliothèque", "/bibliotheque", order=20, match=r"^/bibliotheque"),),
    migrations=MIGRATIONS,
    title="Bibliothèque de procédés",
    description="Structures enregistrées, présets d'étape et briques technologiques à reprendre dans le constructeur.",
    icon="library",
    required=True,
)
