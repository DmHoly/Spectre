"""Structures enregistrées, présets d'étape et briques technologiques (intégrés, partagés, propres
à un µprojet). Pages bibliothèque, présets et briques ; les briques de référence (``/briques``) et
la fiche d'une brique (``/briques/{id}`` : ses versions, où elle sert)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import library_files  # noqa: F401 - déclare presets.yml et briques.yml à la bibliothèque
from . import structure_source  # noqa: F401 - déclare les structures enregistrées comme structures nommées (une plaque en porte une)
from .api import router
from .migrations import MIGRATIONS

LIBRARY_GLYPH = '<path d="M5 4h3v16H5Z"/><path d="M10 4h3v16h-3Z"/><path d="m15.5 4.8 2.9-.8 3.6 15.2-2.9.8Z"/>'
# deux briques empilées : les briques de référence
BRICKS_GLYPH = '<rect x="3" y="4" width="18" height="6" rx="1"/><rect x="3" y="14" width="8" height="6" rx="1"/><rect x="13" y="14" width="8" height="6" rx="1"/>'

PLUGIN = Plugin(
    name="process_library",
    # experiments : où servent les briques (usages.py, les études qui en ont une copie)
    depends_on=("structures", "microprojects", "library", "experiments"),
    router=router,
    pages=(
        Page("/bibliotheque", "library-hub.html"),
        Page("/microprojets/{slug}/presets-etapes", "step-presets.html"),
        Page("/microprojets/{slug}/briques-technologiques", "tech-bricks.html"),
        Page("/briques", "bricks.html"),
        Page("/briques/{brick_id}", "brick.html"),
    ),
    nav=(
        NavEntry("Bibliothèque", "/bibliotheque", order=20, match=r"^/bibliotheque", group="structure", glyph=LIBRARY_GLYPH),
        NavEntry("Briques de réf.", "/briques", order=27, match=r"^/briques", group="structure", glyph=BRICKS_GLYPH),
    ),
    migrations=MIGRATIONS,
    title="Bibliothèque de procédés",
    description="Structures enregistrées, présets d'étape et briques technologiques à reprendre dans le constructeur.",
    icon="library",
    required=True,
)
