"""La barre de chargement du constructeur de structures : une simulation de plusieurs secondes se
suit, étape par étape. Le calcul reste à ``structures``, qui note où il en est sous l'identifiant que
la page lui donne ; ce plugin le lit (``GET /api/simulation-runs/{run}``) et en fait la barre, montée
dans la zone de dessin. Désactivé, le constructeur simule comme avant, sans barre."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(
    name="simulation_progress",
    depends_on=("accounts", "structures"),
    router=router,
    title="Barre de chargement",
    description="Montre l'avancement d'une simulation dans le constructeur - l'étape en cours et le temps écoulé - quand elle prend quelques secondes.",
    icon="progress",
)
