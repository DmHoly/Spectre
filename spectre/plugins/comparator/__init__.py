"""Comparateur de structures : un tableau, une ligne par plaque ou par structure, une colonne par
paramètre, chaque différence avec la ligne de base colorée (modifié, paramètre ajouté, couche en plus,
étape déplacée). La page ``/comparateur`` et chaque page qui compare des structures (évolution d'un
µprojet, d'une référence) s'en servent. Les plaques et les références y déclarent leurs jetons."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

# deux colonnes face à face (l'entrée à icône de la barre du haut, à côté de la session : la
# navigation n'a plus la place d'un libellé de plus)
COMPARE_ICON = '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/><path d="m7.5 10-2 2 2 2"/><path d="m16.5 10 2 2-2 2"/>'

PLUGIN = Plugin(
    name="comparator",
    depends_on=("experiments", "microprojects", "structures"),
    router=router,
    pages=(Page("/comparateur", "comparator.html"),),
    nav=(NavEntry("Comparateur de structures", "/comparateur", order=80, match=r"^/comparateur", icon=COMPARE_ICON),),
    title="Comparateur de structures",
    description="Compare plaques, études et références dans un tableau : un paramètre par colonne, chaque différence avec la base en couleur.",
    icon="compare",
    required=True,
)
