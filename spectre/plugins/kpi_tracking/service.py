"""Les KPI qu'un projet corporate suit, et leur distribution sur toutes ses plaques.

Deux choses distinctes :

- **le choix** : une liste de KPI par projet corporate (:class:`TrackedKpi`), chacun une colonne d'un
  type de données PRISM par plaque (``hook`` + ``column``) prise dans le :func:`catalog` - les
  colonnes de « KPI » que la fiche de chaque hook déclare (``kpi_columns``), pas les coordonnées ni
  les identifiants. Rangé en base, par projet ; tous ses µprojets le partagent ;
- **le calcul** (:func:`distributions`) : à la demande, jamais stocké. On remonte les plaques de
  **tous les µprojets du projet** (``physical_tracking`` de la pointe de chaque piste) ; chaque type
  de données est interrogé **une fois** pour toutes ces plaques (par paquets du plafond de
  ``characterization``), et pour chaque KPI et chaque plaque on garde la distribution de la colonne
  sur ses lignes (les dispositifs mesurés) : quartiles, moustaches à 1,5 × l'écart interquartile et
  valeurs aberrantes - de quoi tracer une boîte à moustaches par plaque. Le cache par plaque de PRISM
  fait que seule une plaque nouvelle ou ``refresh`` retape la base.

Un type de données en échec (base injoignable, colonne disparue de la requête) n'ôte rien aux autres
KPI : le KPI concerné porte son ``status`` et son message, les autres leurs distributions. Comme les
tendances du projet (:mod:`spectre.plugins.kpis`), la lecture est ouverte à tout compte connecté ;
le titre d'une étude, lui, ne se montre qu'à qui peut lire son µprojet.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, DomainError, InvalidInput, NotFound
from ..accounts.service import User
from ..characterization import service as characterization
from ..experiments.entities import compact
from ..experiments.repository import branch_tips, get_repository
from ..areas.service import ManagementArea
from ..microprojects import service as microprojects

log = logging.getLogger(__name__)

MAX_KPIS = 30  # des boîtes à moustaches : au-delà, la page n'est plus lisible
MAX_LABEL = 80
MAX_OUTLIERS = 50  # par plaque et par KPI : de quoi les montrer, sans faire grossir la réponse d'un wafer très dispersé

# Les colonnes d'un type de données qui sont de l'identification ou de la position, pas une mesure.
NOT_A_KPI = {"wafername", "wafer_name", "wafer name", "x", "y", "srgb"}
WAFER_COLUMNS = ("wafername", "wafer_name", "wafer name")


@dataclass(frozen=True)
class CatalogKpi:
    """Un KPI qu'un projet peut suivre : une colonne de KPI d'un type de données par plaque de PRISM."""

    hook: str
    column: str
    hook_title: str
    unit: str = ""
    description: str = ""

    @property
    def key(self) -> str:
        return f"{self.hook}:{self.column}"


@dataclass(frozen=True)
class TrackedKpi:
    id: int
    hook: str
    column: str
    label: str  # le nom d'affichage choisi ; vide : la colonne
    position: int
    created_at: str  # SQLite « YYYY-MM-DD HH:MM:SS », UTC

    @property
    def title(self) -> str:
        return self.label or self.column


@dataclass(frozen=True)
class BoxStats:
    n: int
    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    mean: float
    whisker_low: float  # la plus petite valeur dans [Q1 - 1,5 IQR ; Q3 + 1,5 IQR]
    whisker_high: float


@dataclass(frozen=True)
class WaferDistribution:
    wafer: str  # la plaque telle qu'une étude la nomme
    microprojects: list[dict[str, str]]  # [{slug, name}] : les µprojets dont une étude la suit
    studies: list[dict[str, str | None]]  # [{microproject, experiment_id, title}] ; title None : étude d'un µprojet illisible
    stats: BoxStats | None  # None : aucune mesure de ce KPI sur cette plaque
    outliers: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class KpiDistribution:
    kpi: TrackedKpi
    status: str  # ok | error | unavailable
    unit: str = ""
    description: str = ""
    hook_title: str = ""
    message: str = ""
    groups: list[WaferDistribution] = field(default_factory=list)


@dataclass(frozen=True)
class Distributions:
    source: str | None  # "prism" ou "demo" ; None si rien n'a été interrogé
    wafers: list[dict[str, Any]]
    kpis: list[KpiDistribution]


# --- le catalogue -------------------------------------------------------------------------------


def _column_names(declared: str) -> list[str]:
    """Une colonne de KPI de la fiche peut en nommer deux (« V at Max EQE / I at Max EQE »)."""
    return [name.strip() for name in declared.split(" / ") if name.strip()]


def catalog() -> list[CatalogKpi]:
    """Les KPI disponibles : les colonnes de KPI des types de données implémentés qui se requêtent
    par plaque (et par plaque seulement - un type qui demande autre chose, un numéro de FDL, ne se
    rattache pas aux plaques d'un projet)."""
    kpis: list[CatalogKpi] = []
    for data_type in characterization.list_types(status="implemented", by_wafer=True):
        if tuple(data_type.parameters) != (characterization.WAFER_PARAMETER,):
            continue
        seen: set[str] = set()
        for column in data_type.kpi_columns:
            for name in _column_names(str(column.get("name") or "")):
                if name.lower() in NOT_A_KPI or name in seen:
                    continue
                seen.add(name)
                kpis.append(
                    CatalogKpi(
                        hook=data_type.key,
                        column=name,
                        hook_title=data_type.title,
                        unit=str(column.get("unit") or ""),
                        description=str(column.get("description") or ""),
                    )
                )
    return kpis


def _catalog_entry(hook: str, column: str) -> CatalogKpi | None:
    return next((k for k in catalog() if k.hook == hook and k.column == column), None)


# --- le choix du projet ------------------------------------------------------------------------


def _tracked(row) -> TrackedKpi:
    return TrackedKpi(row["id"], row["hook"], row["column_name"], row["label"], row["position"], row["created_at"])


def list_tracked(area: ManagementArea) -> list[TrackedKpi]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM area_tracked_kpis WHERE area_id = ? ORDER BY position, id", (area.id,)
        ).fetchall()
    return [_tracked(row) for row in rows]


def _clean_label(label: str | None) -> str:
    label = " ".join((label or "").split())
    if len(label) > MAX_LABEL:
        raise InvalidInput(f"Un nom de KPI fait {MAX_LABEL} caractères au plus.", code="label_too_long")
    return label


def add_tracked(area: ManagementArea, user: User, hook: str, column: str, label: str | None = None) -> TrackedKpi:
    """Suit ``column`` de ``hook`` : elle doit être au catalogue (422 ``unknown_kpi`` sinon), une fois par projet
    (409 ``kpi_already_tracked``)."""
    if _catalog_entry(hook, column) is None:
        raise InvalidInput(f"« {column} » de « {hook} » n'est pas un KPI disponible.", code="unknown_kpi")
    label = _clean_label(label)
    with get_conn() as conn:
        count, last = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(position), -1) FROM area_tracked_kpis WHERE area_id = ?",
            (area.id,),
        ).fetchone()
        if count >= MAX_KPIS:
            raise InvalidInput(f"{MAX_KPIS} KPI suivis au plus par projet.", code="too_many_kpis")
        exists = conn.execute(
            "SELECT 1 FROM area_tracked_kpis WHERE area_id = ? AND hook = ? AND column_name = ?",
            (area.id, hook, column),
        ).fetchone()
        if exists:
            raise Conflict("Ce KPI est déjà suivi par le projet.", code="kpi_already_tracked")
        cursor = conn.execute(
            "INSERT INTO area_tracked_kpis (area_id, hook, column_name, label, position, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (area.id, hook, column, label, last + 1, user.id),
        )
        row = conn.execute("SELECT * FROM area_tracked_kpis WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _tracked(row)


def _get_tracked(conn, area: ManagementArea, kpi_id: int):
    row = conn.execute(
        "SELECT * FROM area_tracked_kpis WHERE id = ? AND area_id = ?", (kpi_id, area.id)
    ).fetchone()
    if row is None:
        raise NotFound("KPI suivi inconnu pour ce projet.")
    return row


def rename_tracked(area: ManagementArea, kpi_id: int, label: str) -> TrackedKpi:
    label = _clean_label(label)
    with get_conn() as conn:
        _get_tracked(conn, area, kpi_id)
        conn.execute("UPDATE area_tracked_kpis SET label = ? WHERE id = ?", (label, kpi_id))
        row = _get_tracked(conn, area, kpi_id)
    return _tracked(row)


def remove_tracked(area: ManagementArea, kpi_id: int) -> None:
    with get_conn() as conn:
        _get_tracked(conn, area, kpi_id)
        conn.execute("DELETE FROM area_tracked_kpis WHERE id = ?", (kpi_id,))


# --- le calcul ----------------------------------------------------------------------------------


def _quantile(sorted_values: list[float], fraction: float) -> float:
    """Quantile à interpolation linéaire (celui de numpy, par défaut) d'une liste triée non vide."""
    position = (len(sorted_values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def box_stats(values: list[float]) -> tuple[BoxStats, list[float]] | None:
    """Les statistiques d'une boîte à moustaches et ses valeurs aberrantes (hors des moustaches, les plus
    éloignées d'abord, ``MAX_OUTLIERS`` au plus) ; ``None`` sans valeur."""
    if not values:
        return None
    ordered = sorted(values)
    q1, median, q3 = (_quantile(ordered, f) for f in (0.25, 0.5, 0.75))
    spread = 1.5 * (q3 - q1)
    inside = [v for v in ordered if q1 - spread <= v <= q3 + spread]
    outliers = sorted((v for v in ordered if not q1 - spread <= v <= q3 + spread), key=lambda v: -abs(v - median))
    stats = BoxStats(
        n=len(ordered),
        minimum=ordered[0],
        q1=q1,
        median=median,
        q3=q3,
        maximum=ordered[-1],
        mean=sum(ordered) / len(ordered),
        whisker_low=inside[0],
        whisker_high=inside[-1],
    )
    return stats, outliers[:MAX_OUTLIERS]


def _number(value: Any) -> float | None:
    """Une cellule en nombre fini, ou ``None`` (vide, texte, booléen, vecteur - une courbe n'est pas un KPI)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def tracked_wafers(area: ManagementArea, user: User) -> dict[str, dict[str, Any]]:
    """Les plaques que les µprojets du projet suivent, par clé de plaque (:func:`compact`) :
    ``{wafer, microprojects, studies}``, dans l'ordre des µprojets puis des pistes. Une plaque suivie par
    deux études n'y est qu'une fois, avec ses deux études. Le titre d'une étude est celui qu'un
    lecteur de son µprojet voit : ``None`` pour qui ne peut pas le lire."""
    wafers: dict[str, dict[str, Any]] = {}
    for microproject in sorted(microprojects.list_by_management_area(area.id), key=lambda m: (m.created_at or "", m.id)):  # le plus ancien d'abord
        readable = microprojects.has_role(user, microproject, "viewer")
        for tip in branch_tips(get_repository(microproject.slug)):
            for entry in tip.metadata.get("physical_tracking", []):
                name = (entry.get("sample_id") or "").strip()
                if not name:
                    continue
                found = wafers.setdefault(compact(name), {"wafer": name, "microprojects": [], "studies": []})
                ref = {"slug": microproject.slug, "name": microproject.name}
                if ref not in found["microprojects"]:
                    found["microprojects"].append(ref)
                study = {"microproject": microproject.slug, "experiment_id": tip.branch, "title": tip.title if readable else None}
                if study not in found["studies"]:
                    found["studies"].append(study)
    return wafers


def _failed(kpi: TrackedKpi, entry: CatalogKpi | None, status: str, message: str) -> KpiDistribution:
    return KpiDistribution(
        kpi, status, entry.unit if entry else "", entry.description if entry else "", entry.hook_title if entry else "", message
    )


def _query_hook(hook: str, wafers: list[str], refresh: bool) -> tuple[str, list[str], list[list[Any]]]:
    """Tous les résultats du type de données ``hook`` pour ``wafers`` (par paquets du plafond d'une requête)."""
    source, columns, rows = "", [], []
    for start in range(0, len(wafers), characterization.MAX_WAFERS):
        chunk = wafers[start : start + characterization.MAX_WAFERS]
        result = characterization.query(hook, {characterization.WAFER_PARAMETER: chunk}, refresh=refresh)
        source, columns = result.source, result.columns
        rows.extend(result.rows)
    return source, columns, rows


def _values_by_wafer(columns: list[str], rows: list[list[Any]], column: str) -> dict[str, list[float]]:
    lower = [c.lower() for c in columns]
    wafer_at = next((lower.index(name) for name in WAFER_COLUMNS if name in lower), None)
    if wafer_at is None:
        raise InvalidInput("la requête ne dit pas à quelle plaque va chaque ligne")
    if column not in columns:
        raise InvalidInput(f"la colonne « {column} » n'est plus dans la requête")
    value_at = columns.index(column)
    by_wafer: dict[str, list[float]] = {}
    for row in rows:
        number = _number(row[value_at])
        if number is not None and row[wafer_at]:
            by_wafer.setdefault(compact(str(row[wafer_at])), []).append(number)
    return by_wafer


def distributions(area: ManagementArea, user: User, *, refresh: bool = False) -> Distributions:
    """La distribution de chaque KPI suivi sur chaque plaque suivie - voir le docstring du module."""
    tracked = list_tracked(area)
    wafers = tracked_wafers(area, user)
    catalogue = {k.key: k for k in catalog()} if tracked else {}
    queries: dict[str, tuple[str, list[str], list[list[Any]]] | Exception] = {}
    sources: set[str] = set()
    results: list[KpiDistribution] = []
    for kpi in tracked:
        entry = catalogue.get(f"{kpi.hook}:{kpi.column}")
        if entry is None:
            results.append(_failed(kpi, None, "unavailable", "Ce KPI n'est plus au catalogue PRISM."))
            continue
        if not wafers:  # rien à interroger : le KPI est là, sans boîte
            results.append(KpiDistribution(kpi, "ok", entry.unit, entry.description, entry.hook_title))
            continue
        if kpi.hook not in queries:
            try:
                queries[kpi.hook] = _query_hook(kpi.hook, [w["wafer"] for w in wafers.values()], refresh)
            except Exception as exc:  # une base injoignable ne prive pas des autres types de données
                queries[kpi.hook] = exc
        outcome = queries[kpi.hook]
        if isinstance(outcome, Exception):
            if isinstance(outcome, DomainError):
                message = str(outcome)
            else:
                log.exception("KPI suivi %s:%s du projet %s : calcul impossible", kpi.hook, kpi.column, area.slug, exc_info=outcome)
                message = "Calcul impossible pour le moment : l'erreur a été journalisée sur le serveur."
            results.append(_failed(kpi, entry, "error", message))
            continue
        source, columns, rows = outcome
        sources.add(source)
        try:
            by_wafer = _values_by_wafer(columns, rows, kpi.column)
        except InvalidInput as exc:
            results.append(_failed(kpi, entry, "error", str(exc)))
            continue
        groups = []
        for key, wafer in wafers.items():
            computed = box_stats(by_wafer.get(key, []))
            groups.append(
                WaferDistribution(wafer["wafer"], wafer["microprojects"], wafer["studies"], computed[0] if computed else None, computed[1] if computed else [])
            )
        results.append(KpiDistribution(kpi, "ok", entry.unit, entry.description, entry.hook_title, groups=groups))
    return Distributions(
        source=sorted(sources)[0] if len(sources) == 1 else ("mixed" if sources else None),
        wafers=list(wafers.values()),
        kpis=results,
    )
