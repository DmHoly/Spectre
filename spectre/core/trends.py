"""Trend KPIs of a corporate project (management area) - one monthly time series per KPI, drawn by
the reusable tabbed block on the project page (``static/js/kpi-trend.js``).

The point of this module is the *registry*: each KPI is a :class:`KpiDefinition` with a
``provider`` that turns (area, months) into monthly points. Adding a KPI = one ``register(...)``
call; the API (:mod:`spectre.api.management`) and the front's tabs pick it up with no other change.

A KPI without provider yet is a **placeholder**: it appears as a tab, says where its data will come
from (typically a PRISM hook, see :mod:`spectre.api.datahook`), and returns no points. Wiring it
later means writing its provider - e.g. run the hook on the wafers tracked by the area's µprojets
(``physical_tracking`` of each branch tip) and average the KPI column per month.

A KPI can also run on **demo** data (``demo=True``, see :mod:`spectre.core.demo_trends`): fictitious
but plausible numbers, always labelled as such on the page, to show what the view will look like
before its real source is wired. A KPI can offer **variants** - the same trend counted differently
(experiments in progress vs wafers engaged), switched by a toggle on the page.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Literal

from . import microprojects
from .management import ManagementArea

Status = Literal["live", "placeholder", "demo", "error"]


@dataclass(frozen=True)
class TrendPoint:
    period: str  # "YYYY-MM"
    value: float | None  # None = no measurement that month (a gap, not a zero)
    study: str | None = None  # a study behind this point, whose fiche the page can open (demo data)
    label: str | None = None  # what that study changed, shown on hover


@dataclass(frozen=True)
class TrendResult:
    status: Status
    points: list[TrendPoint] = field(default_factory=list)
    target: float | None = None  # optional reference line (e.g. from an objective)
    message: str = ""


Provider = Callable[[ManagementArea, int, str | None], TrendResult]  # (area, months, variant key)


@dataclass(frozen=True)
class KpiVariant:
    """One way of counting a KPI's trend (e.g. experiments in progress / wafers engaged)."""

    key: str
    label: str
    unit: str = ""
    description: str = ""


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
    variants: tuple[KpiVariant, ...] = ()  # the first one is the default
    demo: bool = False  # the provider serves fictitious demonstration data (see demo_trends)

    @property
    def status(self) -> Status:
        if self.provider is None:
            return "placeholder"
        return "demo" if self.demo else "live"

    def variant(self, key: str | None) -> KpiVariant | None:
        """The variant ``key`` (the default one when ``None``); ``KeyError`` if unknown."""
        if not self.variants:
            if key:
                raise KeyError(key)
            return None
        if key is None:
            return self.variants[0]
        for variant in self.variants:
            if variant.key == key:
                return variant
        raise KeyError(key)


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


def series(key: str, area: ManagementArea, months: int, variant: str | None = None) -> TrendResult:
    """``variant`` must already be validated against the KPI (see :meth:`KpiDefinition.variant`)."""
    kpi = get_kpi(key)
    if kpi.provider is None:
        return TrendResult(status="placeholder", message="Source de données pas encore branchée.")
    chosen = kpi.variant(variant)
    try:
        return kpi.provider(area, months, chosen.key if chosen else None)
    except Exception as exc:  # a provider talks to Follow repos / PRISM - never a raw trace to the page
        return TrendResult(status="error", message=f"calcul impossible : {exc}")


# --- providers --------------------------------------------------------------------------------


def _month_bounds(periods: list[str]) -> list[tuple[datetime, datetime]]:
    """Each ``"YYYY-MM"`` period as ``[start, end)`` instants (UTC)."""
    bounds = []
    for period in periods:
        year, month = (int(part) for part in period.split("-"))
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        bounds.append((datetime(year, month, 1, tzinfo=timezone.utc), datetime(next_year, next_month, 1, tzinfo=timezone.utc)))
    return bounds


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _tracked_wafers(experiment) -> int:
    return sum(1 for entry in experiment.metadata.get("physical_tracking", []) if entry.get("sample_id"))


def _running_intervals(versions: list) -> list[tuple[datetime, datetime | None]]:
    """When a study (its versions, oldest first) was in progress: from a draft/running version to
    the next concluded/abandoned one (``None`` = still in progress). A conclusion can be reopened
    by a later evolution, hence possibly several intervals."""
    intervals: list[tuple[datetime, datetime | None]] = []
    start: datetime | None = None
    for version in versions:
        moment = _aware(version.created_at)
        running = version.conclusion.status in microprojects.RUNNING_STATUSES
        if running and start is None:
            start = moment
        elif not running and start is not None:
            intervals.append((start, moment))
            start = None
    if start is not None:
        intervals.append((start, None))
    return intervals


def _activity(area: ManagementArea, months: int, variant: str | None) -> TrendResult:
    """Experiments in progress during each month (``variant="running"``), or the real wafers they
    track (``"wafers"``), across every µprojet of the area - computed from Spectre's own data (the
    Follow repositories), no external base needed. An experiment is one line of study (a branch);
    it counts for a month if it was in progress at some point of that month - launched before the
    month ended, not yet concluded or abandoned when it began. A study of a few days thus still
    shows, where a snapshot at each month's end would miss it."""
    periods = month_periods(months)
    bounds = _month_bounds(periods)
    values = [0] * len(periods)
    for microproject in microprojects.list_by_management_area(area.id):
        by_branch: dict[str, list] = defaultdict(list)
        for experiment in microprojects.get_repository(microproject.slug):
            by_branch[experiment.branch].append(experiment)
        for versions in by_branch.values():
            versions.sort(key=lambda e: _aware(e.created_at))
            created = [_aware(e.created_at) for e in versions]
            intervals = _running_intervals(versions)
            for i, (month_start, month_end) in enumerate(bounds):
                if not any(start < month_end and (end is None or end > month_start) for start, end in intervals):
                    continue
                if variant == "wafers":
                    state = versions[bisect_left(created, month_end) - 1]  # last version known that month
                    values[i] += _tracked_wafers(state)
                else:
                    values[i] += 1
    return TrendResult(status="live", points=[TrendPoint(p, float(v)) for p, v in zip(periods, values)])


def _eqe_demo(area: ManagementArea, months: int, variant: str | None) -> TrendResult:
    from .demo_trends import eqe_demo_series

    return eqe_demo_series(area, months)


register(
    KpiDefinition(
        key="activite",
        label="Activité R&D",
        unit="expériences",
        description="Expériences en cours dans le mois, tous µprojets du projet confondus.",
        better="up",
        source="Spectre · dépôts Follow des µprojets",
        provider=_activity,
        variants=(
            KpiVariant(
                "running",
                "Expériences en cours",
                "expériences",
                "Expériences en cours à un moment du mois (lancées, pas encore conclues), tous µprojets du projet confondus.",
            ),
            KpiVariant(
                "wafers",
                "Wafers engagés",
                "wafers",
                "Wafers réels suivis par les expériences en cours dans le mois, tous µprojets du projet confondus.",
            ),
        ),
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
        # Données fictives tant que le hook PRISM eqe n'est pas branché : remplacer par un vrai
        # provider (et retirer demo=True) le moment venu - voir spectre.core.demo_trends.
        provider=_eqe_demo,
        demo=True,
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
