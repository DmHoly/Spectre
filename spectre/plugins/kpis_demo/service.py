"""Demonstration data for a trend KPI whose real source isn't wired yet - today the EQE (the PRISM
``eqe`` hook, see :mod:`spectre.plugins.characterization.api`). **Everything here is fictitious**: plausible numbers
and five made-up "studies" of a GaN nanowire LED, each of which lifted the EQE, so the project page
can show what the trend - and the study fiche behind a point - will look like. The page labels it
as demo data everywhere (status ``"demo"`` in :mod:`spectre.plugins.kpis.service`).

The only real computation is the cross-section of each study's structure: its process is simulated
by StructureForge, exactly like the structure builder does, so the mock fiche draws a genuine
structure.

The plugin is only active with ``SPECTRE_DEMO_DATA=1`` (:func:`enabled`): it then registers its EQE
over the placeholder of :mod:`spectre.plugins.kpis.service` (``kpis.register``); without it, the
EQE tab stays a placeholder and the study fiche route doesn't exist. Remove this plugin's EQE once
the PRISM hook feeds the real one.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field, replace
from datetime import date
from functools import lru_cache
from typing import Any

from structureforge.presentation.svg import frame_to_svg
from structureforge.process.steps import ProcessStep
from pydantic import TypeAdapter

from ...kernel.errors import NotFound
from ..areas.service import ManagementArea
from ..kpis import service as trends
from ..kpis.service import TrendPoint, TrendResult, month_periods
from ..structures.simulation import SubstrateSpec, run_simulation

EQE_TARGET = 10.0  # % - the reference line on the chart ("objectif")


def enabled() -> bool:
    """A demonstration instance: ``SPECTRE_DEMO_DATA=1`` (read at each call - tests switch it)."""
    return os.environ.get("SPECTRE_DEMO_DATA") == "1"

_STEP_LIST = TypeAdapter(list[ProcessStep])


def _length(value: float) -> dict:
    return {"value": value, "unit": "nm"}


def _dep(name: str, material: str, thickness: float, recipe: str = "MOCVD Epitaxial") -> dict:
    return {"kind": "deposition", "name": name, "material": material, "recipe": recipe, "thickness": _length(thickness)}


def _facet(name: str, thickness: float) -> dict:
    return {
        "kind": "faceted_growth",
        "name": name,
        "material": "GaN",
        "thickness": _length(thickness),
        "rate_c": 1.0,
        "rate_m": 0.4,
        "rate_sp": 0.15,
        "semi_polar_angle_deg": 30.0,
        "seed_materials": ["GaN"],
    }


_WIDTH = 300.0
_SUBSTRATE = {"material": "Sapphire", "domain_width": _length(_WIDTH), "thickness": _length(20)}
_BASE = [
    _dep("Tampon AlN", "AlN", 15),
    _dep("Croissance GaN", "GaN", 60),
    {
        "kind": "lithography",
        "name": "Masque des piliers",
        "resist_material": "Photoresist",
        "thickness": _length(80),
        "openings": [[0.0, _WIDTH / 2 - 30], [_WIDTH / 2 + 30, _WIDTH]],
    },
    {"kind": "etch", "name": "Gravure ICP des piliers", "recipe": "Cl2 ICP-RIE (III-N)", "depth": _length(60)},
    {"kind": "resist_strip", "name": "Retrait du masque", "material": "Photoresist"},
    _facet("Croissance facettée 1", 10),
    _facet("Croissance facettée 2", 10),
]


def _active(well: float = 3.0, ebl: bool = False, cap: float = 8.0, passivation: bool = False, ito: float = 15.0) -> list[dict]:
    steps = [_dep("Puits quantique InGaN", "InGaN", well)]
    if ebl:
        steps.append(_dep("EBL AlGaN", "Al0.15Ga0.85N", 5))
    steps.append(_dep("Capot p-GaN", "GaN", cap))
    if passivation:
        steps.append(_dep("Passivation Al2O3", "Al2O3", 4, recipe="ALD Conformal"))
    steps.append(_dep("Contact ITO", "ITO", ito, recipe="Sputter Metal (normal)"))
    return steps


@dataclass(frozen=True)
class DemoStudy:
    id: str
    months_ago: int  # when it concluded, counted back from the current month
    title: str
    change: str  # what it changed versus the previous reference
    eqe: float  # the level it reached (%)
    decision: str  # Follow's Conclusion.decision: promote / inconclusive / branch...
    conclusion: str
    steps: list[dict] = field(repr=False)


STUDIES: tuple[DemoStudy, ...] = (
    DemoStudy(
        "eqe-ref",
        11,
        "Référence nanofil GaN, puits InGaN unique",
        "Point de départ : puits InGaN de 3 nm, capot p-GaN de 8 nm, contact ITO.",
        3.4,
        "promote",
        "Procédé stable et reproductible sur 4 wafers ; sert de référence pour la suite. EQE limité par les fuites d'électrons.",
        _BASE + _active(),
    ),
    DemoStudy(
        "eqe-puits",
        8,
        "Puits quantique aminci à 2,5 nm",
        "Épaisseur du puits InGaN : 3 nm → 2,5 nm (moins d'effet Stark confiné).",
        5.1,
        "promote",
        "Gain net d'EQE (+1,7 pt) et raie d'émission plus étroite ; un puits à 2 nm, testé en parallèle, dégrade l'homogénéité.",
        _BASE + _active(well=2.5),
    ),
    DemoStudy(
        "eqe-ebl",
        6,
        "Couche bloqueuse d'électrons AlGaN",
        "Ajout d'une EBL Al0.15Ga0.85N de 5 nm entre le puits et le capot p-GaN.",
        7.2,
        "promote",
        "Les fuites d'électrons chutent : EQE +2,1 pt, droop réduit à forte densité de courant. Adoptée dans la référence.",
        _BASE + _active(well=2.5, ebl=True),
    ),
    DemoStudy(
        "eqe-passivation",
        3,
        "Passivation ALD Al2O3 des flancs",
        "Dépôt ALD conforme de 4 nm d'Al2O3 sur les flancs des nanofils avant le contact.",
        8.9,
        "promote",
        "Recombinaisons de surface réduites : EQE +1,7 pt, surtout sur les petits diamètres. Une variante SiN reste non concluante.",
        _BASE + _active(well=2.5, ebl=True, passivation=True),
    ),
    DemoStudy(
        "eqe-contact",
        1,
        "Capot aminci et contact ITO recuit",
        "Capot p-GaN 8 → 6 nm, ITO 15 → 20 nm avec recuit sous O2.",
        10.4,
        "promote",
        "Objectif EQE ≥ 10 % atteint sur 3 wafers sur 4 ; à confirmer sur un lot de 8 avant transfert.",
        _BASE + _active(well=2.5, ebl=True, cap=6.0, passivation=True, ito=20.0),
    ),
)

_STUDY_BY_ID = {study.id: study for study in STUDIES}

# Pistes secondaires (abandonnées / non concluantes) de l'arbre symbolique : (id, libellé, parent, statut)
_SIDE_TRIES = (
    ("puits-2nm", "Puits 2 nm", "eqe-puits", "abandoned"),
    ("passivation-sin", "Passivation SiN", "eqe-passivation", "inconclusive"),
)


def _jitter(*parts: str) -> float:
    """A deterministic value in [-1, 1) - the same page always shows the same demo curve."""
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**31 - 1


def _period_months_ago(period: str, today: date) -> int:
    year, month = (int(part) for part in period.split("-"))
    return (today.year - year) * 12 + today.month - month


def eqe_demo_series(area: ManagementArea, months: int, variant: str | None = None, today: date | None = None) -> TrendResult:
    """A rising EQE, month by month (a KPI provider - the EQE has no variant): each study lifts the
    level when it concludes, with a gentle creep and a little noise in between; the months a study
    concluded carry it (``study``), so the page can open its fiche from the chart."""
    today = today or date.today()
    points = []
    for period in month_periods(months, today):
        ago = _period_months_ago(period, today)
        done = [s for s in STUDIES if s.months_ago >= ago]  # already concluded that month
        level = done[-1].eqe if done else 2.6
        upcoming = next((s for s in STUDIES if s.months_ago < ago), None)
        if upcoming is not None:  # glisse doucement vers le jalon suivant
            span = (done[-1].months_ago if done else upcoming.months_ago + 4) - upcoming.months_ago
            progress = (span - (ago - upcoming.months_ago)) / span if span else 0
            level += 0.25 * max(0.0, progress) * (upcoming.eqe - level)
        elif done:  # après la dernière étude : consolidation lente (le procédé se stabilise)
            level += 0.3 * (done[-1].months_ago - ago)
        value = round(level + 0.18 * _jitter(area.slug, period), 2)
        milestone = next((s for s in STUDIES if s.months_ago == ago), None)
        points.append(
            TrendPoint(period, value, study=milestone.id if milestone else None, label=milestone.title if milestone else None)
        )
    return TrendResult(
        status="demo",
        points=points,
        target=EQE_TARGET,
        message="Données fictives de démonstration - le hook PRISM « eqe » n'est pas encore branché.",
    )


@lru_cache(maxsize=None)
def _structure_svg(study_id: str) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    study = _STUDY_BY_ID[study_id]
    _geometry, frames, materials = run_simulation("demo", SubstrateSpec.model_validate(_SUBSTRATE), _STEP_LIST.validate_python(study.steps))
    colors = {m.name: m.color for m in materials}
    final = frames[-1]
    shown = tuple(sorted({layer.material for layer in final.layers}))
    return frame_to_svg(final, colors), shown, tuple((name, colors.get(name, "#999999")) for name in shown)


def _tree(current: str) -> dict[str, Any]:
    """A symbolic experiment tree: the main line of studies (lane 0), and the side tries that
    branched off it (lane 1), with the path leading to ``current`` marked."""
    order = [s.id for s in STUDIES]
    upto = order.index(current)
    nodes = [
        {
            "id": study.id,
            "label": f"v{i + 1}.0",
            "title": study.title,
            "lane": 0,
            "col": i,
            "status": study.decision,
            "state": "current" if i == upto else ("past" if i < upto else "future"),
        }
        for i, study in enumerate(STUDIES)
    ]
    edges = [[order[i], order[i + 1]] for i in range(len(order) - 1)]
    for try_id, label, parent, status in _SIDE_TRIES:
        col = order.index(parent) + 1
        nodes.append({"id": try_id, "label": label, "title": label, "lane": 1, "col": col, "status": status, "state": "past" if col <= upto else "future"})
        edges.append([parent, try_id])
    return {"nodes": nodes, "edges": edges, "current": current}


def demo_study(area: ManagementArea, kpi_key: str, study_id: str, today: date | None = None) -> dict[str, Any]:
    """The mock fiche of one study behind a point of the demo KPI ``kpi_key``."""
    if not trends.get_kpi(kpi_key).demo:
        raise NotFound(f"pas de fiche d'étude pour le KPI {kpi_key!r}")
    study = _STUDY_BY_ID.get(study_id)
    if study is None:
        raise NotFound(f"étude {study_id!r} introuvable")
    today = today or date.today()
    year, month = today.year, today.month - study.months_ago
    while month <= 0:
        year, month = year - 1, month + 12
    svg, materials, colors = _structure_svg(study_id)
    index = [s.id for s in STUDIES].index(study_id)
    previous = STUDIES[index - 1].eqe if index else None
    return {
        "id": study.id,
        "demo": True,
        "title": study.title,
        "project": area.name,
        "microproject": "Nanofils GaN - LED bleue (démo)",
        "period": f"{year:04d}-{month:02d}",
        "change": study.change,
        "result": {"metric": "EQE", "unit": "%", "value": study.eqe, "previous": previous, "target": EQE_TARGET},
        "objective": {
            "name": "EQE à 450 nm",
            "metric": "eqe_pct",
            "direction": "maximize",
            "target": EQE_TARGET,
            "rationale": "Seuil de rendement fixé pour le démonstrateur LED bleue de la période.",
            "status": "atteint" if study.eqe >= EQE_TARGET else "en progrès",
        },
        "conclusion": {"decision": study.decision, "summary": study.conclusion},
        "steps": [step["name"] for step in study.steps],
        "structure_svg": svg,
        "materials": list(materials),
        "material_colors": dict(colors),
        "tree": _tree(study_id),
    }


EQE_DEMO = trends.register(replace(trends.EQE, provider=eqe_demo_series, demo=True, enabled=enabled))
