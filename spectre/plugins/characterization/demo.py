"""La source de démonstration, **uniquement** quand ``SPECTRE_DEMO_DATA=1`` (voir
:func:`spectre.plugins.characterization.service.current_source`) : une instance de démo sans accès
aux bases de caractérisation doit pouvoir montrer la page Data et les vues du cahier. Des jeux
synthétiques mais plausibles, aux mêmes colonnes que les requêtes PRISM (``hook.yml`` de chaque
type) - déterministes par plaque (même lasermark, mêmes données), toujours marqués
``source: "demo"``.

Elle respecte le contrat de la source PRISM qu'elle remplace : elle ne liste que les types qu'elle
sait servir (leurs fiches sont celles du catalogue PRISM, lisibles sans base) et répond 404 pour
tout autre.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta
from typing import Any

from ...kernel.errors import NotFound
from .source import WAFER_PARAMETER, DataSource, DataType, QueryResult


def _rng(*parts: str) -> random.Random:
    seed = int(hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12], 16)
    return random.Random(seed)


def _disc(radius: int, step: int = 1) -> list[tuple[int, int]]:
    return [(x, y) for x in range(-radius, radius + 1, step) for y in range(-radius, radius + 1, step) if x * x + y * y <= radius * radius]


def _logspace(a: float, b: float, n: int) -> list[float]:
    return [10 ** (math.log10(a) + i * (math.log10(b) - math.log10(a)) / (n - 1)) for i in range(n)]


def _eqe(wafers: list[str]) -> tuple[list[str], list[list[Any]]]:
    columns = [
        "wafername", "X", "Y", "Led_Name", "I", "V", "EQE", "max_EQE", "J_at_MaxEQE", "V at Max EQE",
        "yield_per_wafer", "area_cm2", "is_lit", "Lambda_Peak", "FWHM", "EQE_25A_cm2",
    ]
    rows = []
    for wafer in wafers:
        rng = _rng("eqe", wafer)
        peak_eqe = rng.uniform(0.012, 0.03)
        peak_j = rng.uniform(8, 30)
        lam0 = rng.uniform(445, 470)
        devices = _disc(6)
        lit = []
        wafer_rows = []
        for i, (x, y) in enumerate(devices):
            r = math.hypot(x, y) / 6
            dead = rng.random() < 0.03 + 0.08 * r**3
            area = 1.4e-4
            current = _logspace(1e-6, 4e-2, 40)
            eqe_max = 0.0 if dead else peak_eqe * (1 - 0.35 * r**2) * rng.uniform(0.85, 1.12)
            j0 = peak_j * rng.uniform(0.8, 1.25)
            eqe = []
            for amp in current:
                j = amp / area
                eqe.append(round(eqe_max * 2 * math.sqrt(j / j0) / (1 + j / j0), 6))
            volt = [round(2.6 + 0.09 * math.log(amp / 1e-6) + amp * rng.uniform(55, 80), 4) for amp in current]
            best = max(range(len(eqe)), key=lambda k: eqe[k])
            lam = [round(lam0 + 6 * r - 1.5 * math.log10(amp / 1e-6) + rng.uniform(-0.6, 0.6), 2) for amp in current]
            j25 = 25.0
            eqe25 = eqe_max * 2 * math.sqrt(j25 / j0) / (1 + j25 / j0)
            lit.append(not dead)
            wafer_rows.append(
                [
                    wafer, x + 7, y + 7, f"MONO2-118x118-{5800 + i}-R", [round(a, 9) for a in current], volt, eqe,
                    round(max(eqe), 6), round(current[best] / area, 3), volt[best], None, area, not dead, lam,
                    [round(rng.uniform(18, 24), 2)] * len(current), round(eqe25, 6),
                ]
            )
        yield_pct = round(100 * sum(lit) / len(lit), 1)
        for row in wafer_rows:
            row[10] = yield_pct
        rows.extend(wafer_rows)
    return columns, rows


def _pl(wafers: list[str]) -> tuple[list[str], list[list[Any]]]:
    columns = ["wafername", "Wafer name", "PL date", "FDL", "Recipe", "X", "Y", "Dominant WL(nm)", "Peak WL (nm)", "Integrated PL (a.u.)", "FWHM (nm)"]
    rows = []
    for n, wafer in enumerate(wafers):
        rng = _rng("pl", wafer)
        base = rng.uniform(445, 470)
        tilt = (rng.uniform(-3, 3), rng.uniform(-3, 3))
        intensity = rng.uniform(0.6, 1.4)
        day = (date(2026, 9, 1) + timedelta(days=n * 3)).isoformat()
        for x, y in _disc(40, 4):
            r = math.hypot(x, y) / 40
            peak = base + 7 * r**2 + tilt[0] * x / 40 + tilt[1] * y / 40 + rng.uniform(-0.4, 0.4)
            rows.append(
                [
                    wafer, wafer, day, f"FDL-{1200 + n}", "MQW-B3", x, y, round(peak + 2.5, 2), round(peak, 2),
                    round(intensity * (1 - 0.55 * r**2) * rng.uniform(0.9, 1.1) * 1e5, 0), round(19 + 4 * r + rng.uniform(-0.5, 0.5), 2),
                ]
            )
    return columns, rows


def _ncel(wafers: list[str]) -> tuple[list[str], list[list[Any]]]:
    columns = ["wafername", "filter", "Test_Date", "X", "Y", "x_position", "y_position", "na_current_a", "na_emission_max", "na_jpv_max"]
    rows = []
    for wafer in wafers:
        rng = _rng("ncel", wafer)
        level = rng.uniform(0.5, 1.5)
        for x, y in _disc(10):
            r = math.hypot(x, y) / 10
            rows.append(
                [
                    wafer, "450nm", "2026-09-12", x + 11, y + 11, x * 4.5, y * 4.5, round(rng.uniform(1e-4, 3e-4), 7),
                    round(level * (1 - 0.6 * r**2) * rng.uniform(0.8, 1.15), 4), round(rng.uniform(0.2, 0.5), 4),
                ]
            )
    return columns, rows


def _waferlist(wafers: list[str]) -> tuple[list[str], list[list[Any]]]:
    columns = ["wafer_name", "Run_Name", "start_date", "end_date", "Recipe_Type", "reactor"]
    names = wafers or [f"W{n:02d}-DEMO" for n in range(1, 6)]
    rows = []
    for n, wafer in enumerate(names):
        rng = _rng("waferlist", wafer)
        start = date(2026, 8, 1) + timedelta(days=rng.randint(0, 40))
        rows.append([wafer, f"RUN-{2600 + n}", start.isoformat(), (start + timedelta(days=2)).isoformat(), rng.choice(["MQW", "SQW", "Buffer"]), rng.choice(["R1", "R2"])])
    return columns, rows


GENERATORS = {"eqe": _eqe, "pl": _pl, "ncel": _ncel, "waferlist": _waferlist}


class DemoSource:
    name = "demo"

    def __init__(self, catalogue: DataSource) -> None:
        self._catalogue = catalogue  # les fiches documentaires (PRISM)

    def list_types(self) -> list[DataType]:
        return [t for t in self._catalogue.list_types() if t.key in GENERATORS and t.implemented]

    def describe(self, key: str) -> DataType:
        if key not in GENERATORS:
            raise NotFound(f"type de données inconnu : {key}")
        return self._catalogue.describe(key)

    def query(self, key: str, parameters: dict[str, list[str]], *, refresh: bool = False) -> QueryResult:
        generator = GENERATORS.get(key)
        if generator is None:
            raise NotFound(f"type de données inconnu : {key}")
        columns, rows = generator(parameters.get(WAFER_PARAMETER, []))
        return QueryResult(source=self.name, columns=columns, rows=rows)

    def chart(self, key: str, chart_key: str) -> bytes:
        self.describe(key)
        return self._catalogue.chart(key, chart_key)
