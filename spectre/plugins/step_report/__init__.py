"""Les commentaires d'étape et le rapport pas à pas du constructeur de structures : chaque étape d'un
procédé peut porter un commentaire (rangé ici, sous l'id de l'étape, ``/api/microprojects/{slug}/step-comments``),
et le constructeur propose de télécharger un rapport - un diaporama HTML d'une seule page, une diapositive
par étape. Le rapport se fabrique côté page, à partir de ce que le constructeur a déjà à l'écran (le dessin
de chaque étape, ses paramètres, la légende des matériaux) ; ce plugin n'apporte que les commentaires.
Désactivé, le constructeur est celui d'avant : pas de champ « Commentaire », pas de bouton de rapport."""

from ...kernel.plugin import Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="step_report",
    depends_on=("accounts", "microprojects", "structures"),
    router=router,
    migrations=MIGRATIONS,
    title="Commentaires et rapport d'étapes",
    description="Un commentaire sur chaque étape du procédé, et un rapport à télécharger : un diaporama étape par étape (dessin, paramètres, commentaire, légende des couleurs).",
    icon="clipboard",
)
