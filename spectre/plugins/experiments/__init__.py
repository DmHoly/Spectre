"""Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut,
conclusion, étiquettes, entités physiques, fusion, suppression, diff, filiation et refs."""

from ...kernel.plugin import Page, Plugin
from .api import page_router, router

PLUGIN = Plugin(
    name="experiments",
    depends_on=("microprojects", "structures", "attachments"),
    router=router,
    page_router=page_router,  # un ancien lien vers un id de version -> la page de sa piste
    pages=(
        Page("/microprojets/{slug}/experiences/{experiment_id}", "experiment.html"),
        Page("/microprojets/{slug}/refs", "refs.html"),
    ),
)
