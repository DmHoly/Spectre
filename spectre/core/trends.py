"""Trend KPIs of a corporate project (management area) - one monthly time series per KPI, drawn by
the reusable tabbed block on the project page (``static/js/kpi-trend.js``).

The point of this module is the *registry*: each KPI is a :class:`KpiDefinition` with a
``provider`` that turns (area, months) into monthly points. Adding a KPI = one ``register(...)``
call; the API (:mod:`spectre.api.management`) and the front's tabs pick it up with no other change.

A KPI without provider yet is a **placeholder**: it appears as a tab, says where its data will come
from (typically a PRISM hook, see :mod:`spectre.api.datahook`), and returns no points. Wiring it
later means writing its provider - e.g. run the hook on the wafers tracked by the area's µprojets
(``physical_tracking`` of each branch tip) and average the KPI column per month.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Literal

from . import microprojects
from .management import ManagementArea

Status = Literal["live", "placeholder", "error"]


@dataclass(frozen=True)
class TrendPoint:
    period: str  # "YYYY-MM"
    value: float | None  # None = no measurement that month (a gap, not a zero)


@dataclass(frozen=True)
class TrendResult:
    status: Status
    points: list[TrendPoint] = field(default_factory=list)
    target: float | None = None  # optional reference line (e.g. from an objective)
    message: str = ""


Provider = Callable[[ManagementArea, int], TrendResult]


@dataclass(frozen=True)
class KpiDefinition:
    key: str
    label: str
    unit: str = ""
    description: str = ""
    better: Literal["up", "down"] | None = None  # which way is good, for the delta colouring
    source: str = ""  # where the numbers come from, shown under the chart
    hook: str | None = None  # PRISM hook key the KPI is (or will be) computed from
    provider: Provider | None = None

    @property
    def status(self) -> Status:
        return "live" if self.provider else "placeholder"


_REGISTRY: dict[str, KpiDefinition] = {}


def register(kpi: KpiDefinition) -> KpiDefinition:
    _REGISTRY[kpi.key] = kpi
    return kpi


def list_kpis() -> list[KpiDefinition]:
    return list(_REGISTRY.values())


def get_kpi(key: str) -> KpiDefinition:
    return _REGISTRY[key]  # KeyError -> 404 in the API


def month_periods(months: int, today: date | None = None) -> list[str]:
    """The last ``months`` calendar months, oldest first, current month included."""
    today = today or date.today()
    year, month = today.year, today.month
    periods = []
    for _ in range(months):
        periods.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return periods[::-1]


def series(key: str, area: ManagementArea, months: int) -> TrendResult:
    kpi = get_kpi(key)
    if kpi.provider is None:
        return TrendResult(status="placeholder", message="Source de données pas encore branchée.")
    try:
        return kpi.provider(area, months)
    except Exception as exc:  # a provider talks to Follow repos / PRISM - never a raw trace to the page
        return TrendResult(status="error", message=f"calcul impossible : {exc}")


# --- providers --------------------------------------------------------------------------------


def _activity(area: ManagementArea, months: int) -> TrendResult:
    """Experiment versions committed per month across every µprojet of the area - the one KPI
    Spectre can compute from its own data (Follow repositories), no external base needed."""
    periods = month_periods(months)
    counts: Counter[str] = Counter()
    for microproject in microprojects.list_by_management_area(area.id):
        for exp in microprojects.get_repository(microproject.slug):
            counts[exp.created_at.strftime("%Y-%m")] += 1
    return TrendResult(status="live", points=[TrendPoint(p, float(counts.get(p, 0))) for p in periods])


register(
    KpiDefinition(
        key="activite",
        label="Activité R&D",
        unit="versions",
        description="Versions d'expériences enregistrées par mois, tous µprojets du projet confondus.",
        better="up",
        source="Spectre · dépôts Follow des µprojets",
        provider=_activity,
    )
)
register(
    KpiDefinition(
        key="eqe",
        label="EQE",
        unit="%",
        description="Rendement quantique externe moyen des wafers suivis, par mois de mesure.",
        better="up",
        source="PRISM · hook eqe",
        hook="eqe",
    )
)
register(
    KpiDefinition(
        key="pl",
        label="Photoluminescence",
        unit="u.a.",
        description="Intensité PL moyenne des wafers suivis, par mois de mesure.",
        better="up",
        source="PRISM · hook pl",
        hook="pl",
    )
)
register(
    KpiDefinition(
        key="defauts",
        label="Défectivité",
        unit="déf./cm²",
        description="Densité de défauts moyenne des wafers suivis, par mois d'inspection.",
        better="down",
        source="PRISM · hook defect_counting",
        hook="defect_counting",
    )
)
register(
    KpiDefinition(
        key="rendement",
        label="Rendement",
        unit="%",
        description="Part des puces fonctionnelles au test électrique, par mois.",
        better="up",
        source="À définir",
    )
)
