"""Lumière, le moteur de rapports (``lumiere_report``), dans Spectre : **un seul chemin pour un rapport**. Un
rapport est un *modèle* (:mod:`.templates` : des slides, un bloc Lumière par cellule) appliqué à un *contexte*
(aujourd'hui une plaque ; demain une analyse, une étude, un lot). Le bouton « Rapport » d'une page liste les
modèles de son contexte et lance la génération en tâche de fond (:mod:`.service`) ; le fichier HTML autonome
(Plotly, cartes, suivi de plaque) se télécharge depuis la page ou depuis « Rapports » du menu Data, où tous
les rapports générés se retrouvent. Le plugin n'existe que si ``lumiere_report`` est installé (:mod:`.engine`),
et PRISM est le même pour les deux (voir SOCLE-DATA.md §4.6)."""

from ...kernel.plugin import NavEntry, Page, Plugin
from . import engine
from .api import router
from .migrations import MIGRATIONS

REPORT_GLYPH = '<path d="M14 3v5h5"/><path d="M6 3h8l5 5v13H6z"/><path d="M9 13h6"/><path d="M9 17h6"/>'

PLUGIN = Plugin(
    name="lumiere",
    depends_on=("accounts", "wafers", "characterization", "wafer_data", "sem_images"),
    router=router,
    pages=(Page("/lumiere", "lumiere.html"),),
    nav=(NavEntry("Rapports", "/lumiere", order=46, match=r"^/lumiere", group="data", glyph=REPORT_GLYPH),),
    migrations=MIGRATIONS,
    enabled=engine.available,
    title="Rapports Lumière",
    description="Des rapports HTML autonomes générés par le moteur Lumière à partir des données de Spectre : un bouton « Rapport » sur la page d'une plaque, des modèles de rapport, l'historique des rapports générés.",
    icon="file",
)
