"""Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut,
conclusion, étiquettes, entités physiques, fusion, suppression, diff, filiation et refs."""

from ...kernel.plugin import Page, Plugin
from .api import router

PLUGIN = Plugin(
    name="experiments",
    depends_on=("microprojects", "structures", "attachments"),
    router=router,
    pages=(
        Page("/microprojets/{slug}/experiences/{experience_id}", "experience.html"),
        Page("/microprojets/{slug}/refs", "refs.html"),
    ),
)
