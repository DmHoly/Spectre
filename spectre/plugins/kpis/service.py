"""Trend KPIs of a corporate project (management area) - one monthly time series per KPI, drawn by
the reusable tabbed block on the project page (``plugins/kpis/static/kpi-trend.js``).

The point of this module is the *registry*: each KPI is a :class:`KpiDefinition` with a
``provider`` that turns (area, months) into monthly points. Adding a KPI = one ``register(...)``
call, from the plugin that owns its data; the API (:mod:`spectre.plugins.kpis.api`) and the front's
tabs pick it up with no other change. The « activité » KPI is registered here (this plugin depends
on experiments), the demo EQE by :mod:`spectre.plugins.kpis_demo.service`.

A KPI without provider yet is a **placeholder**: it appears as a tab, says where its data will come
from (typically a PRISM hook, see :mod:`spectre.plugins.characterization.api`), and returns no points. Wiring it
later means writing its provider - e.g. run the hook on the wafers tracked by the area's µprojets
(``physical_tracking`` of each branch tip) and average the KPI column per month.

A KPI can also run on **demo** data (``demo=True``, see :mod:`spectre.plugins.kpis_demo.service`): fictitious
but plausible numbers, always labelled as such on the page, to show what the view will look like
before its real source is wired - registered under the key of the placeholder it stands in for, and
only in force while its ``enabled()`` holds (``SPECTRE_DEMO_DATA=1``). A KPI can offer **variants** -
the same trend counted differently (experiments in progress vs wafers engaged), switched by a
toggle on the page.
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Literal

from ...kernel.errors import InvalidInput, NotFound
from ..areas.service import ManagementArea
from ..experiments.insights import tracked_wafers
from ..experiments.repository import RUNNING_STATUSES, get_repository
from ..microprojects import service as microprojects

log = logging.getLogger(__name__)

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
    demo: bool = False  # the provider serves fictitious demonstration data (see kpis_demo)
    enabled: Callable[[], bool] = lambda: True  # while False, the definition registered before it under the same key stands

    @property
    def status(self) -> Status:
        if self.provider is None:
            return "placeholder"
        return "demo" if self.demo else "live"

    def variant(self, key: str | None) -> KpiVariant | None:
        """The variant ``key`` (the default one when ``None``); :class:`InvalidInput` if unknown."""
        if key is None:
            return self.variants[0] if self.variants else None
        for variant in self.variants:
            if variant.key == key:
                return variant
        raise InvalidInput(f"variante {key!r} inconnue pour le KPI {self.key!r}")


# Each key's definitions, in registration order: the last one enabled is the KPI.
_REGISTRY: dict[str, list[KpiDefinition]] = {}


def register(kpi: KpiDefinition) -> KpiDefinition:
    _REGISTRY.setdefault(kpi.key, []).append(kpi)
    return kpi


def _current(definitions: list[KpiDefinition]) -> KpiDefinition | None:
    return next((kpi for kpi in reversed(definitions) if kpi.enabled()), None)


def list_kpis() -> list[KpiDefinition]:
    return [kpi for kpi in map(_current, _REGISTRY.values()) if kpi is not None]


def get_kpi(key: str) -> KpiDefinition:
    kpi = _current(_REGISTRY.get(key, []))
    if kpi is None:
        raise NotFound(f"KPI {key!r} inconnu")
    return kpi


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


def series(kpi: KpiDefinition, area: ManagementArea, months: int, variant: KpiVariant | None = None) -> TrendResult:
    """``variant`` is one of the KPI's (see :meth:`KpiDefinition.variant`)."""
    if kpi.provider is None:
        return TrendResult(status="placeholder", message="Source de données pas encore branchée.")
    try:
        return kpi.provider(area, months, variant.key if variant else None)
    except Exception:  # a provider talks to Follow repos / PRISM: the trace goes to the log, never to the page
        log.exception("KPI %s du projet %s : calcul impossible", kpi.key, area.slug)
        return TrendResult(status="error", message="Calcul impossible pour le moment : l'erreur a été journalisée sur le serveur.")


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


def _running_intervals(versions: list) -> list[tuple[datetime, datetime | None]]:
    """When a study (its versions, oldest first) was in progress: from a draft/running version to
    the next concluded/abandoned one (``None`` = still in progress). A conclusion can be reopened
    by a later evolution, hence possibly several intervals."""
    intervals: list[tuple[datetime, datetime | None]] = []
    start: datetime | None = None
    for version in versions:
        moment = _aware(version.created_at)
        running = version.conclusion.status in RUNNING_STATUSES
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
    track (``"wafers"``, each wafer once - see :func:`tracked_wafers`), across every µprojet of the
    area - computed from Spectre's own data (the Follow repositories), no external base needed. An
    experiment is one line of study (a branch); it counts for a month if it was in progress at some
    point of that month - launched before the month ended, not yet concluded or abandoned when it
    began. A study of a few days thus still shows, where a snapshot at each month's end would miss it."""
    periods = month_periods(months)
    bounds = _month_bounds(periods)
    in_progress: list[list] = [[] for _ in periods]  # per month, the last version known of each study in progress
    for microproject in microprojects.list_by_management_area(area.id):
        by_branch: dict[str, list] = defaultdict(list)
        for experiment in get_repository(microproject.slug):
            by_branch[experiment.branch].append(experiment)
        for versions in by_branch.values():
            versions.sort(key=lambda e: _aware(e.created_at))
            created = [_aware(e.created_at) for e in versions]
            intervals = _running_intervals(versions)
            for i, (month_start, month_end) in enumerate(bounds):
                if any(start < month_end and (end is None or end > month_start) for start, end in intervals):
                    in_progress[i].append(versions[bisect_left(created, month_end) - 1])
    if variant == "wafers":
        values = [len(tracked_wafers(states)) for states in in_progress]
    else:
        values = [len(states) for states in in_progress]
    return TrendResult(status="live", points=[TrendPoint(p, float(v)) for p, v in zip(periods, values)])


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
# Sans provider tant que le hook PRISM eqe n'est pas branché ; une instance de démonstration le
# remplace par des données fictives (spectre.plugins.kpis_demo.service).
EQE = register(
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
