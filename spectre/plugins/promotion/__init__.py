"""Promotion de référence : choisir une structure comme nouvelle référence (ou nouvelle version
d'une référence), par un formulaire dédié - la page ``/promotion`` - que chaque étude, variante de
split, conclusion, page d'évolution et page de référence ouvre déjà rempli. Les règles vérifiées
avant de promouvoir sont un registre (:mod:`.rules`) : une règle de plus ne change ni le formulaire,
ni l'API. Chaque promotion est gardée au journal, avec son pourquoi et les verdicts des règles."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router
from .migrations import MIGRATIONS

PLUGIN = Plugin(
    name="promotion",
    depends_on=("experiments", "microprojects", "structures", "references"),
    router=router,
    pages=(Page("/promotion", "promotion.html"),),
    nav=(NavEntry("Promouvoir une réf.", "/promotion", order=26, match=r"^/promotion", id="nav-promotion"),),
    migrations=MIGRATIONS,
    title="Promotion de référence",
    description="Choisir une structure comme référence : un formulaire dédié, ouvert depuis chaque étude, split ou conclusion, avec ses règles et son journal.",
    icon="bookmark",
)
