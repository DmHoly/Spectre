"""Les types de données de caractérisation : le catalogue (filtré, ou regroupé par catégorie), la
fiche d'un type, une requête pour des plaques et les graphiques documentaires.

La source est PRISM, ou la démo avec ``SPECTRE_DEMO_DATA=1`` (instance sans accès aux bases) -
jamais en repli silencieux d'une base injoignable. :func:`current_source` est le seul endroit qui
choisit ; tout ce qui suit vaut pour les deux sources, à commencer par la vérification des
paramètres et le plafond de plaques d'une requête. C'est aussi l'interface des autres plugins
(le cahier de données, ``notebook``).
"""

from __future__ import annotations

import os
from dataclasses import replace

from ...kernel.errors import InvalidInput
from .demo import DemoSource
from .prism_source import PrismSource
from .source import WAFER_PARAMETER, DataSource, DataType, QueryResult

# Plafond de plaques d'une requête, quel que soit l'appelant (page Data, cahier de données).
MAX_WAFERS = 50

_PRISM = PrismSource()
_DEMO = DemoSource(catalogue=_PRISM)


def demo_enabled() -> bool:
    return os.environ.get("SPECTRE_DEMO_DATA") == "1"


def current_source() -> DataSource:
    return _DEMO if demo_enabled() else _PRISM


def list_types(*, category: str | None = None, status: str | None = None, by_wafer: bool | None = None) -> list[DataType]:
    return [
        t
        for t in current_source().list_types()
        if (category is None or t.category == category)
        and (status is None or t.status == status)
        and (by_wafer is None or t.by_wafer == by_wafer)
    ]


def categories() -> list[tuple[str, list[DataType]]]:
    """Les types regroupés par catégorie (« Post EPI », « Structure »...), implémentés et à venir
    mêlés, dans l'ordre où chaque catégorie apparaît au catalogue."""
    grouped: dict[str, list[DataType]] = {}
    for data_type in current_source().list_types():
        grouped.setdefault(data_type.category, []).append(data_type)
    return list(grouped.items())


def describe(key: str) -> DataType:
    return current_source().describe(key)


def chart(key: str, chart_key: str) -> bytes:
    return current_source().chart(key, chart_key)


def _wafer_names(values: list[str]) -> list[str]:
    names = list(dict.fromkeys(v.strip() for v in values if v and v.strip()))
    if not names:
        raise InvalidInput("indiquez au moins une plaque (lasermark)")
    if len(names) > MAX_WAFERS:
        raise InvalidInput(f"{MAX_WAFERS} plaques au plus par requête ({len(names)} demandées)")
    return names


def _checked_parameters(data_type: DataType, parameters: dict[str, list[str]]) -> dict[str, list[str]]:
    """Les paramètres que le type déclare, vérifiés ; les autres sont ignorés, comme le fait PRISM
    (un même jeu de paramètres sert à plusieurs types)."""
    if not data_type.implemented:
        raise InvalidInput("ce type de données n'est pas encore disponible (fiche documentaire)", code="not_implemented")
    missing = [p for p in data_type.parameters if p not in parameters]
    if missing:
        raise InvalidInput(f"paramètre(s) manquant(s) : {', '.join(missing)}")
    checked = {p: list(parameters[p]) for p in data_type.parameters}
    if data_type.by_wafer:
        checked[WAFER_PARAMETER] = _wafer_names(checked[WAFER_PARAMETER])
    return checked


def query(key: str, parameters: dict[str, list[str]], *, refresh: bool = False) -> QueryResult:
    """La requête ``key`` : ``refresh`` ignore le cache par plaque (sans effet sur un type non mis
    en cache). Le résultat porte les plaques réellement demandées (nettoyées, sans doublon)."""
    source = current_source()
    checked = _checked_parameters(source.describe(key), parameters)
    result = source.query(key, checked, refresh=refresh)
    return replace(result, wafers=checked.get(WAFER_PARAMETER, []))
