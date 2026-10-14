"""Plaques jumelles : parmi toutes les plaques suivies de vos µprojets, celles dont la structure est
exactement celle d'une ligne de référence - ou n'en diffère que d'une ou deux variations, à la
demande. Le panneau se monte sur la page du comparateur, qui y ajoute les plaques trouvées."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(
    name="twins",
    depends_on=("experiments", "comparator", "wafers"),
    router=router,
    title="Plaques jumelles",
    description="Trouve les plaques de même structure qu'une ligne du comparateur, ou à une ou deux variations près, et les ajoute à la comparaison.",
    icon="layers",
)
