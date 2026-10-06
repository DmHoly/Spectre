"""Les µprojets dans la recherche de la barre du haut (:mod:`spectre.plugins.search`) : par numéro
tel qu'on le dit (« Nat 4 », « Nat_0004 », « nat4 ») ou par un bout de son nom, pour tout compte
connecté - la même visibilité, à l'échelle de la société, que les pages des projets corporate (la
page d'un µprojet garde ses propres règles d'accès)."""

from __future__ import annotations

from urllib.parse import quote

from ..accounts.service import User
from ..areas import service as areas
from ..search.service import SearchHit, SearchProvider, register_provider
from . import service


def _microprojects(query: str, user: User) -> list[SearchHit]:
    found = service.search(query)
    if not found:
        return []
    area_names = {area.id: area.name for area in areas.list_all()}
    return [
        SearchHit(
            label=microproject.code or microproject.name,
            detail=microproject.name if microproject.code else "",
            badge=area_names.get(microproject.management_area_id, ""),
            url=f"/microprojets/{quote(microproject.slug, safe='')}",
        )
        for microproject in found
    ]


register_provider(SearchProvider(type="microproject", plugin="microprojects", search=_microprojects, order=10))
