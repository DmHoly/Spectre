"""La recherche de la barre du haut : un registre de fournisseurs (:func:`register_provider`), chacun
déclaré par le plugin qui possède ses données - microprojects, wafers (lasermark et FDL), lots -, et
:func:`search`, qui les interroge et met leurs résultats bout à bout, groupe par groupe. Ce plugin ne
connaît aucun type cherchable : chaque fournisseur décide de ce qu'il trouve, de ce que le lecteur a
le droit d'en voir et de l'adresse de la page à ouvrir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from ...kernel.errors import InvalidInput
from ..accounts.service import User


@dataclass(frozen=True)
class SearchHit:
    """Un résultat : ``label`` en tête (un numéro, un code, un lasermark), ``detail`` à côté, ``badge``
    à droite, et ``url``, la page qu'il ouvre."""

    label: str
    url: str
    detail: str = ""
    badge: str = ""


def _never(query: str) -> bool:
    return False


@dataclass(frozen=True)
class SearchProvider:
    type: str  # le groupe de ses résultats : « microproject », « lot », « wafer », « fdl »
    search: Callable[[str, User], list[SearchHit]]  # ce qu'il trouve pour cette saisie, vu par ce lecteur
    order: int = 100  # rang de son groupe
    leads: Callable[[str], bool] = _never  # son groupe passe en tête pour cette saisie (« 1234 » : une FDL)


_PROVIDERS: dict[str, SearchProvider] = {}


def register_provider(provider: SearchProvider) -> None:
    _PROVIDERS[provider.type] = provider


def search(query: str, user: User, types: list[str] | None = None) -> list[dict]:
    """``[{type, label, detail, badge, url}]`` : les résultats de chaque fournisseur (ceux de
    ``types`` seulement, s'il est donné), groupe par groupe."""
    unknown = sorted(set(types or ()) - _PROVIDERS.keys())
    if unknown:
        raise InvalidInput(f"Type de recherche inconnu : {', '.join(unknown)} (connus : {', '.join(sorted(_PROVIDERS))}).")
    query = query.strip()
    if not query:
        return []
    selected = sorted(
        (provider for provider in _PROVIDERS.values() if not types or provider.type in types),
        key=lambda provider: (not provider.leads(query), provider.order, provider.type),
    )
    return [{"type": provider.type, **asdict(hit)} for provider in selected for hit in provider.search(query, user)]
