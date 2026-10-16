"""Le résumé d'un bloc sur une plaque, calculé sur les lignes que PRISM rend pour elle (``columns`` +
``rows``, une ligne par dispositif ou point de mesure) : fonctions pures, sans base ni PRISM.

Chaque résumé est petit par construction (voir :mod:`.store`) : nombres à 4 chiffres significatifs, une
cartographie ramenée à :data:`MAX_GRID` cases de côté, un histogramme en :data:`HISTOGRAM_BINS` classes,
une courbe en :data:`CURVE_POINTS` points. Une plaque mesurée à plusieurs dates (la colonne « date » du type
de données) n'en garde, par défaut, que la plus récente (``date: "latest"``) ; ``"all"`` les mêle.
"""

from __future__ import annotations

import math
from typing import Any

from ...kernel.errors import InvalidInput
from ..kpi_tracking.service import _date_column, _day, _matches, _number, box_stats

MAX_GRID = 64
HISTOGRAM_BINS = 30
CURVE_POINTS = 60
WAFER_COLUMNS = ("wafername", "wafer_name", "wafer name")


def round4(value: float) -> float:
    return float(f"{value:.4g}")


def _r(value: float | None) -> float | None:
    return None if value is None else round4(value)


def select_rows(columns: list[str], rows: list[list[Any]], filters: list[dict[str, Any]], date: str = "latest") -> tuple[list[list[Any]], str | None, list[str]]:
    """Les lignes qui passent tous les filtres - de la mesure la plus récente seulement (``date`` « latest »)
    quand le type de données a une colonne de date. Rend aussi ce jour et tous les jours mesurés."""
    missing = [f["column"] for f in filters if f["column"] not in columns]
    if missing:
        raise InvalidInput(f"la colonne de filtre « {missing[0]} » n'est plus dans la requête")
    tests = [(columns.index(f["column"]), f["op"], f["value"]) for f in filters]
    kept = [row for row in rows if all(_matches(row[at], op, value) for at, op, value in tests)]
    date_at = _date_column(columns)
    if date_at is None:
        return kept, None, []
    days = sorted({d for row in kept if (d := _day(row[date_at]))})
    if date != "latest" or not days:
        return kept, None, days
    return [row for row in kept if _day(row[date_at]) == days[-1]], days[-1], days


def _at(columns: list[str], column: str) -> int:
    if column not in columns:
        raise InvalidInput(f"la colonne « {column} » n'est plus dans la requête")
    return columns.index(column)


def _numbers(rows: list[list[Any]], at: int) -> list[float]:
    return [n for row in rows if (n := _number(row[at])) is not None]


def _truthy(cell: Any) -> bool | None:
    if cell is None or isinstance(cell, (list, tuple, dict)):
        return None
    if isinstance(cell, bool):
        return cell
    if isinstance(cell, (int, float)):
        return None if isinstance(cell, float) and not math.isfinite(cell) else cell != 0
    text = str(cell).strip().lower()
    if text in ("true", "vrai", "oui", "yes", "1", "ok", "pass"):
        return True
    if text in ("false", "faux", "non", "no", "0", "ko", "fail"):
        return False
    return None


AGGREGATES = ("median", "mean", "min", "max", "std", "count", "share")


def value(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], float | None]:
    """Une valeur : l'agrégat d'une colonne sur les lignes gardées. ``share`` : la part des lignes « vraies »
    (``is_lit``, un test passé) en %. Rend (statut, résumé, valeur à situer parmi les plaques)."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    at = _at(columns, config["column"])
    aggregate = config.get("aggregate", "median")
    base = {"date": day, "dates": days}
    if aggregate == "share":
        flags = [f for row in kept if (f := _truthy(row[at])) is not None]
        if not flags:
            return "empty", {**base, "n": 0}, None
        result = 100.0 * sum(flags) / len(flags)
        return "ok", {**base, "value": round4(result), "n": len(flags)}, result
    numbers = _numbers(kept, at)
    if aggregate == "count":
        result = float(len(numbers))
        return ("ok" if numbers else "empty"), {**base, "value": result, "n": len(numbers)}, result if numbers else None
    if not numbers:
        return "empty", {**base, "n": 0}, None
    if aggregate == "mean":
        result = sum(numbers) / len(numbers)
    elif aggregate == "min":
        result = min(numbers)
    elif aggregate == "max":
        result = max(numbers)
    elif aggregate == "std":
        mean = sum(numbers) / len(numbers)
        result = math.sqrt(sum((n - mean) ** 2 for n in numbers) / (len(numbers) - 1)) if len(numbers) > 1 else 0.0
    else:
        stats = box_stats(numbers)[0]
        result = stats.median
    return "ok", {**base, "value": round4(result), "n": len(numbers)}, result


def histogram(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    numbers = _numbers(kept, _at(columns, config["column"]))
    base = {"date": day, "dates": days}
    if not numbers:
        return "empty", {**base, "n": 0}, None
    stats, _ = box_stats(numbers)
    low, high = min(numbers), max(numbers)
    bins = HISTOGRAM_BINS
    counts = [0] * bins
    if high > low:
        width = (high - low) / bins
        for n in numbers:
            counts[min(int((n - low) / width), bins - 1)] += 1
    else:
        counts[0] = len(numbers)
    return "ok", {
        **base, "n": len(numbers), "minimum": round4(low), "maximum": round4(high), "counts": counts,
        "median": round4(stats.median), "q1": round4(stats.q1), "q3": round4(stats.q3), "mean": round4(stats.mean),
    }, None


def _axis(values: list[float]) -> tuple[list[float], Any]:
    """Les positions d'un axe de cartographie : les valeurs distinctes s'il y en a peu, sinon
    :data:`MAX_GRID` classes égales. Rend les centres et la fonction valeur -> indice."""
    distinct = sorted(set(values))
    if len(distinct) <= MAX_GRID:
        index = {v: i for i, v in enumerate(distinct)}
        return [round4(v) for v in distinct], index.__getitem__
    low, high = distinct[0], distinct[-1]
    width = (high - low) / MAX_GRID
    centres = [round4(low + (i + 0.5) * width) for i in range(MAX_GRID)]
    return centres, lambda v: min(int((v - low) / width), MAX_GRID - 1)


def wafermap(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Une cartographie : la colonne par position (``x``, ``y``), moyenne par case - ``values[j][i]`` à
    ``ys[j]``, ``xs[i]``, ``None`` pour une case sans mesure."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    at, x_at, y_at = _at(columns, config["column"]), _at(columns, config["x"]), _at(columns, config["y"])
    points = [(x, y, v) for row in kept if None not in (x := _number(row[x_at]), y := _number(row[y_at]), v := _number(row[at]))]
    base = {"date": day, "dates": days}
    if not points:
        return "empty", {**base, "n": 0}, None
    xs, x_index = _axis([p[0] for p in points])
    ys, y_index = _axis([p[1] for p in points])
    sums = [[0.0] * len(xs) for _ in ys]
    counts = [[0] * len(xs) for _ in ys]
    for x, y, v in points:
        i, j = x_index(x), y_index(y)
        sums[j][i] += v
        counts[j][i] += 1
    grid = [[round4(sums[j][i] / counts[j][i]) if counts[j][i] else None for i in range(len(xs))] for j in range(len(ys))]
    numbers = [p[2] for p in points]
    stats, _ = box_stats(numbers)
    return "ok", {
        **base, "n": len(points), "xs": xs, "ys": ys, "values": grid,
        "minimum": round4(stats.minimum), "maximum": round4(stats.maximum), "median": round4(stats.median),
        "q1": round4(stats.q1), "q3": round4(stats.q3),
    }, None


def _vector(cell: Any) -> list[float] | None:
    if not isinstance(cell, (list, tuple)) or len(cell) < 2:
        return None
    out = [_number(v) for v in cell]
    return None if any(v is None for v in out) else out  # type: ignore[return-value]


def _interpolate(xs: list[float], ys: list[float], at: float) -> float | None:
    """y en ``at`` sur la courbe (xs, ys) - xs triés croissants -, ``None`` hors de son étendue."""
    if at < xs[0] or at > xs[-1]:
        return None
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= at:
            lo = mid
        else:
            hi = mid
    if xs[hi] == xs[lo]:
        return ys[lo]
    t = (at - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + t * (ys[hi] - ys[lo])


def _quantile(sorted_values: list[float], fraction: float) -> float:
    position = (len(sorted_values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def curve(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Une courbe : chaque ligne porte une courbe (deux colonnes vectorielles, ``x`` et ``y`` - le courant et
    l'EQE d'une LED) ; on garde la médiane et l'enveloppe 10-90 % de toutes, sur :data:`CURVE_POINTS` abscisses
    communes (espacées en log si ``log_x``)."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    x_at, y_at = _at(columns, config["x"]), _at(columns, config["y"])
    log_x = bool(config.get("log_x"))
    curves = []
    for row in kept:
        xs, ys = _vector(row[x_at]), _vector(row[y_at])
        if xs is None or ys is None or len(xs) != len(ys):
            continue
        pairs = sorted((x, y) for x, y in zip(xs, ys) if not log_x or x > 0)
        if len(pairs) >= 2:
            curves.append(([p[0] for p in pairs], [p[1] for p in pairs]))
    base = {"date": day, "dates": days}
    if not curves:
        vectors = any(isinstance(row[x_at], (list, tuple)) for row in kept)
        return "empty", {**base, "n": 0, "reason": "" if vectors or not kept else "not_vectors"}, None
    low = min(c[0][0] for c in curves)
    high = max(c[0][-1] for c in curves)
    if log_x:
        a, b = math.log10(low), math.log10(high)
        grid = [10 ** (a + (b - a) * i / (CURVE_POINTS - 1)) for i in range(CURVE_POINTS)]
    else:
        grid = [low + (high - low) * i / (CURVE_POINTS - 1) for i in range(CURVE_POINTS)]
    median, lower, upper, xs = [], [], [], []
    for at in grid:
        values = sorted(v for c in curves if (v := _interpolate(c[0], c[1], at)) is not None)
        if not values:
            continue
        xs.append(round4(at))
        median.append(round4(_quantile(values, 0.5)))
        lower.append(round4(_quantile(values, 0.1)))
        upper.append(round4(_quantile(values, 0.9)))
    return "ok", {**base, "n": len(curves), "x": xs, "median": median, "low": lower, "high": upper, "log_x": log_x, "log_y": bool(config.get("log_y"))}, None


COMPUTE = {"value": value, "histogram": histogram, "wafermap": wafermap, "curve": curve}
