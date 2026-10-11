"""Structures enregistrées, présets d'étape et briques technologiques (intégrés, partagés, propres
à un µprojet). Pages bibliothèque, présets et briques."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import library_files  # noqa: F401 - déclare presets.yml et briques.yml à la bibliothèque
from .api import router
from .migrations import MIGRATIONS

LIBRARY_GLYPH = '<path d="M5 4h3v16H5Z"/><path d="M10 4h3v16h-3Z"/><path d="m15.5 4.8 2.9-.8 3.6 15.2-2.9.8Z"/>'

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
    nav=(NavEntry("Bibliothèque", "/bibliotheque", order=20, match=r"^/bibliotheque", group="structure", glyph=LIBRARY_GLYPH),),
    migrations=MIGRATIONS,
    title="Bibliothèque de procédés",
    description="Structures enregistrées, présets d'étape et briques technologiques à reprendre dans le constructeur.",
    icon="library",
    required=True,
)
