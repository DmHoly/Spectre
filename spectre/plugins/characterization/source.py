"""Le contrat d'une source de données de caractérisation (``DataSource``) et ce que ses
implémentations partagent : le type de données décrit (``DataType``), le résultat d'une requête
(``QueryResult``) et la conversion d'une cellule en JSON (``json_safe``).

Deux implémentations : PRISM (:mod:`.prism_source`, les vraies bases) et la démo (:mod:`.demo`,
``SPECTRE_DEMO_DATA=1``). Le choix entre elles est fait à un seul endroit,
:func:`spectre.plugins.characterization.service.current_source`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

# Le paramètre qui fait d'un type de données une requête « par plaque » (une liste de lasermarks).
WAFER_PARAMETER = "wafer_names"


@dataclass(frozen=True)
class DataType:
    """Un type de données tel que sa fiche le décrit (``hook.yml`` de PRISM)."""

    key: str
    title: str
    description: str
    category: str
    status: str  # "implemented" (une requête existe) ou "planned" (fiche documentaire seule)
    parameters: tuple[str, ...] = ()
    cacheable: bool = False
    postprocessing: tuple[str, ...] = ()
    raw_columns: tuple[dict[str, Any], ...] = ()
    kpi_columns: tuple[dict[str, Any], ...] = ()
    example_rows: tuple[dict[str, Any], ...] = ()
    representative_column: str | None = None
    charts: tuple[dict[str, Any], ...] = ()  # {key, title, description}

    @property
    def by_wafer(self) -> bool:
        return WAFER_PARAMETER in self.parameters

    @property
    def implemented(self) -> bool:
        return self.status == "implemented"

    def summary(self) -> dict[str, Any]:
        """La forme légère, celle des listes."""
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "status": self.status,
            "by_wafer": self.by_wafer,
            "representative_column": self.representative_column,
        }


@dataclass(frozen=True)
class QueryResult:
    source: str  # "prism" ou "demo" : une donnée de démonstration le dit toujours
    columns: list[str]
    rows: list[list[Any]]
    # Requête mise en cache par plaque : les plaques relues du cache et celles requêtées.
    from_cache: list[str] | None = None
    fetched: list[str] | None = None
    wafers: list[str] = field(default_factory=list)


class DataSource(Protocol):
    """Ce que sait faire une source. Chaque méthode lève ``NotFound`` pour un type (ou un graphique)
    qu'elle ne sert pas ; ``query`` reçoit des paramètres déjà vérifiés par le service."""

    name: str

    def list_types(self) -> list[DataType]: ...

    def describe(self, key: str) -> DataType: ...

    def query(self, key: str, parameters: dict[str, list[str]], *, refresh: bool = False) -> QueryResult: ...

    def chart(self, key: str, chart_key: str) -> bytes: ...


def json_safe(value: Any) -> Any:
    """Une cellule (de DataFrame, ou d'exemple YAML) en quelque chose que ``json.dumps`` accepte,
    sans changer sa forme : NaN, NaT et infinis -> None, vecteur ou scalaire numpy -> Python,
    horodatage -> ISO."""
    if isinstance(value, float):  # float, numpy.float64
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):  # ndarray, scalaire numpy
        return json_safe(value.tolist())
    if pd.isna(value):  # None, NaT, pd.NA, Decimal("NaN")
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
