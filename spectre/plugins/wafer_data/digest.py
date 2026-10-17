"""Le résumé d'un bloc sur une plaque, calculé sur les lignes que PRISM rend pour elle (``columns`` +
``rows``, une ligne par dispositif ou point de mesure) : fonctions pures, sans base ni PRISM.

Chaque résumé est petit par construction (voir :mod:`.store`) : nombres à 4 chiffres significatifs, une
cartographie ramenée à :data:`MAX_GRID` cases de côté, un histogramme en :data:`HISTOGRAM_BINS` classes,
une courbe en :data:`CURVE_POINTS` points, un nuage en :data:`MAX_POINTS` points, :data:`MAX_CURVES`
courbes montrées une à une. Une plaque mesurée à plusieurs dates (la colonne « date » du type de données)
n'en garde, par défaut, que la plus récente (``date: "latest"``) ; ``"all"`` les mêle.

La couleur (``color_by``) et les groupes (``group_by``) rangent les lignes par valeur d'une colonne : au plus
:data:`MAX_GROUPS` groupes, les plus fréquents - le reste dans « Autres ».
"""

from __future__ import annotations

import math
import os
from collections import Counter
from typing import Any

from ...kernel.errors import InvalidInput
from ..kpi_tracking.service import _date_column, _day, _matches, _number, box_stats

MAX_GRID = 64
HISTOGRAM_BINS = 30
CURVE_POINTS = 60
MAX_POINTS = 1000
MAX_CURVES = 40
MAX_GROUPS = 8
MAX_CURVE_GROUPS = 6  # une médiane et son enveloppe par groupe : au-delà, illisible
MAX_BOX_OUTLIERS = 20
WAFER_COLUMNS = ("wafername", "wafer_name", "wafer name")
OTHERS = "Autres"
EMPTY = "(vide)"


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


# --- les groupes (couleur) ------------------------------------------------------------------------


def label(cell: Any) -> str:
    """Le nom d'un groupe : la valeur de la cellule, lisible."""
    if cell is None or (isinstance(cell, float) and not math.isfinite(cell)):
        return EMPTY
    if isinstance(cell, bool):
        return "vrai" if cell else "faux"
    if isinstance(cell, float):
        return f"{round4(cell):g}"
    if isinstance(cell, (list, tuple, dict)):
        return "(vecteur)"
    return str(cell).strip() or EMPTY


def _order(name: str) -> tuple:
    """Les groupes dans un ordre naturel : les nombres par valeur, les textes par ordre alphabétique,
    « (vide) » puis « Autres » à la fin."""
    if name == OTHERS:
        return (3, 0.0, "")
    if name == EMPTY:
        return (2, 0.0, "")
    try:
        return (0, float(name), "")
    except ValueError:
        return (1, 0.0, name.casefold())


def grouping(rows: list[list[Any]], at: int | None, limit: int = MAX_GROUPS) -> tuple[list[str], list[int]]:
    """Les groupes de ``rows`` selon la colonne ``at`` (``None`` : un seul groupe, sans nom) et l'indice du
    groupe de chaque ligne. Au-delà de ``limit`` valeurs, les plus fréquentes gardent leur groupe, les
    autres vont dans « Autres »."""
    if at is None:
        return [""], [0] * len(rows)
    labels = [label(row[at]) for row in rows]
    counts = Counter(labels)
    if len(counts) <= limit:
        kept = set(counts)
    else:
        kept = {name for name, _ in counts.most_common(limit - 1)}
    names = sorted({name if name in kept else OTHERS for name in labels}, key=_order)
    index = {name: i for i, name in enumerate(names)}
    return names, [index[name if name in kept else OTHERS] for name in labels]


def _group_at(columns: list[str], config: dict[str, Any], key: str) -> int | None:
    return _at(columns, config[key]) if config.get(key) else None


def spread(member: list[int], limit: int) -> list[int]:
    """Au plus ``limit`` indices de lignes, répartis équitablement entre les groupes (``member`` : le groupe de
    chaque ligne) puis à intervalles réguliers dans chaque groupe - jamais un pas fixe sur toutes les lignes, qui
    tomberait toujours sur le même groupe quand les lignes alternent (600, 800, 1000, 600...)."""
    if len(member) <= limit:
        return list(range(len(member)))
    by_group: dict[int, list[int]] = {}
    for i, g in enumerate(member):
        by_group.setdefault(g, []).append(i)
    quota = dict.fromkeys(by_group, 0)
    left = limit
    while left:
        hungry = [g for g in by_group if quota[g] < len(by_group[g])]
        for g in hungry[:left]:
            quota[g] += 1
        left -= min(len(hungry), left)
    chosen = []
    for g, rows in by_group.items():
        n = quota[g]
        chosen += [rows[round(k * (len(rows) - 1) / (n - 1))] for k in range(n)] if n > 1 else rows[:n]
    return sorted(set(chosen))


# --- les résumés ----------------------------------------------------------------------------------

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
    """La distribution d'un scalaire en :data:`HISTOGRAM_BINS` classes ; avec ``color_by``, les mêmes classes
    comptées par groupe (``groups`` et ``series``, une liste de comptes par groupe) - à empiler."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    at = _at(columns, config["column"])
    kept = [row for row in kept if _number(row[at]) is not None]
    numbers = [_number(row[at]) for row in kept]
    base = {"date": day, "dates": days}
    if not numbers:
        return "empty", {**base, "n": 0}, None
    stats, _ = box_stats(numbers)
    low, high = min(numbers), max(numbers)
    bins = HISTOGRAM_BINS
    width = (high - low) / bins if high > low else 0.0
    slot = (lambda n: min(int((n - low) / width), bins - 1)) if width else (lambda n: 0)
    names, member = grouping(kept, _group_at(columns, config, "color_by"))
    series = [[0] * bins for _ in names]
    for n, g in zip(numbers, member):
        series[g][slot(n)] += 1
    counts = [sum(s[i] for s in series) for i in range(bins)]
    out = {
        **base, "n": len(numbers), "minimum": round4(low), "maximum": round4(high), "counts": counts,
        "median": round4(stats.median), "q1": round4(stats.q1), "q3": round4(stats.q3), "mean": round4(stats.mean),
    }
    if config.get("color_by"):
        out["groups"], out["series"] = names, series
    return "ok", out, None


def boxplot(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Une boîte à moustaches par groupe (``group_by``), une seule sinon : quartiles, moustaches à 1,5 × l'écart
    interquartile, les valeurs aberrantes les plus éloignées (:data:`MAX_BOX_OUTLIERS` par boîte)."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    at = _at(columns, config["column"])
    log_y = bool(config.get("log_y"))
    kept = [row for row in kept if (n := _number(row[at])) is not None and (not log_y or n > 0)]
    base = {"date": day, "dates": days, "log_y": log_y}
    if not kept:
        return "empty", {**base, "n": 0}, None
    names, member = grouping(kept, _group_at(columns, config, "group_by"), limit=12)
    values: list[list[float]] = [[] for _ in names]
    for row, g in zip(kept, member):
        values[g].append(_number(row[at]))
    boxes = []
    for name, group in zip(names, values):
        if not group:
            continue
        stats, outliers = box_stats(group)
        boxes.append(
            {
                "label": name, "n": stats.n, "minimum": round4(stats.minimum), "maximum": round4(stats.maximum),
                "whisker_low": round4(stats.whisker_low), "q1": round4(stats.q1), "median": round4(stats.median),
                "q3": round4(stats.q3), "whisker_high": round4(stats.whisker_high), "mean": round4(stats.mean),
                "outliers": [round4(v) for v in outliers[:MAX_BOX_OUTLIERS]],
            }
        )
    return "ok", {**base, "n": len(kept), "boxes": boxes}, None


def scatter(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Un nuage : un point par ligne (``x``, ``y`` deux scalaires), ``[x, y, groupe]`` - au plus
    :data:`MAX_POINTS`, pris à pas réguliers dans l'ordre des lignes au-delà."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    x_at, y_at = _at(columns, config["x"]), _at(columns, config["y"])
    log_x, log_y = bool(config.get("log_x")), bool(config.get("log_y"))
    pairs = []
    for row in kept:
        x, y = _number(row[x_at]), _number(row[y_at])
        if x is None or y is None or (log_x and x <= 0) or (log_y and y <= 0):
            continue
        pairs.append((row, x, y))
    base = {"date": day, "dates": days, "log_x": log_x, "log_y": log_y}
    if not pairs:
        return "empty", {**base, "n": 0}, None
    names, member = grouping([p[0] for p in pairs], _group_at(columns, config, "color_by"))
    points = [[round4(pairs[i][1]), round4(pairs[i][2]), member[i]] for i in spread(member, MAX_POINTS)]
    return "ok", {**base, "n": len(pairs), "shown": len(points), "points": points, "groups": names if config.get("color_by") else []}, None


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


# --- les courbes ----------------------------------------------------------------------------------


def _vector(cell: Any) -> list[float | None] | None:
    """Un vecteur de nombres - un point manquant (un NaN de PRISM : l'EQE sous le seuil d'allumage) vaut
    ``None`` et sera sauté, il ne fait pas rejeter la courbe."""
    if not isinstance(cell, (list, tuple)) or len(cell) < 2:
        return None
    if any(isinstance(v, (list, tuple, dict, str, bool)) for v in cell):
        return None
    return [_number(v) for v in cell]


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


def _grid(low: float, high: float, log_x: bool) -> list[float]:
    if log_x:
        a, b = math.log10(low), math.log10(high)
        return [10 ** (a + (b - a) * i / (CURVE_POINTS - 1)) for i in range(CURVE_POINTS)]
    return [low + (high - low) * i / (CURVE_POINTS - 1) for i in range(CURVE_POINTS)]


def _envelope(curves: list[tuple[list[float], list[float]]], grid: list[float]) -> dict[str, list[float]]:
    """La médiane et l'enveloppe 10-90 % de ``curves`` (abscisses triées) sur les abscisses ``grid``."""
    median, lower, upper, xs = [], [], [], []
    for at in grid:
        values = sorted(v for c in curves if (v := _interpolate(c[0], c[1], at)) is not None)
        if not values:
            continue
        xs.append(round4(at))
        median.append(round4(_quantile(values, 0.5)))
        lower.append(round4(_quantile(values, 0.1)))
        upper.append(round4(_quantile(values, 0.9)))
    return {"x": xs, "median": median, "low": lower, "high": upper}


def _thin(points: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    """Au plus ``limit`` points d'une courbe, pris à pas réguliers, le dernier gardé."""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def curve(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Des courbes : chaque ligne en porte une (deux colonnes vectorielles, ``x`` et ``y`` - la tension et
    l'EQE d'une LED). Toujours : la médiane et l'enveloppe 10-90 % de toutes (``x``, ``median``, ``low``,
    ``high``) sur :data:`CURVE_POINTS` abscisses communes (espacées en log si ``log_x``). Avec ``color_by`` :
    la même chose par groupe (``series``). En mode ``curves`` : chacune (``curves``, :data:`MAX_CURVES` au
    plus, à pas réguliers) avec son groupe. Un point manquant d'un vecteur est sauté."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    x_at, y_at = _at(columns, config["x"]), _at(columns, config["y"])
    log_x, log_y = bool(config.get("log_x")), bool(config.get("log_y"))
    found: list[tuple[list[Any], list[tuple[float, float]]]] = []
    for row in kept:
        xs, ys = _vector(row[x_at]), _vector(row[y_at])
        if xs is None or ys is None:
            continue
        points = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and (not log_x or x > 0) and (not log_y or y > 0)]
        if len(points) >= 2:
            found.append((row, points))
    base = {"date": day, "dates": days, "log_x": log_x, "log_y": log_y, "mode": config.get("mode", "envelope")}
    if not found:
        vectors = any(isinstance(row[x_at], (list, tuple)) and isinstance(row[y_at], (list, tuple)) for row in kept)
        return "empty", {**base, "n": 0, "reason": "" if vectors or not kept else "not_vectors"}, None
    ordered = [sorted(points) for _, points in found]
    curves = [([p[0] for p in c], [p[1] for p in c]) for c in ordered]
    grid = _grid(min(c[0][0] for c in curves), max(c[0][-1] for c in curves), log_x)
    out = {**base, "n": len(curves), **_envelope(curves, grid)}
    colored = bool(config.get("color_by"))
    names, member = grouping([row for row, _ in found], _group_at(columns, config, "color_by"), limit=MAX_CURVE_GROUPS if base["mode"] == "envelope" else MAX_GROUPS)
    if colored:
        out["groups"] = names
        if base["mode"] == "envelope":
            out["series"] = [
                {"label": name, "n": len(mine), **_envelope(mine, grid)}
                for g, name in enumerate(names)
                if (mine := [c for c, m in zip(curves, member) if m == g])
            ]
    if base["mode"] == "curves":
        out["curves"] = [
            {"g": member[i], "x": [round4(x) for x, _ in thin], "y": [round4(y) for _, y in thin]}
            for i in spread(member, MAX_CURVES)
            if (thin := _thin(found[i][1], CURVE_POINTS))
        ]
    return "ok", out, None


# --- les images d'une colonne ---------------------------------------------------------------------


def images(columns: list[str], rows: list[list[Any]], config: dict[str, Any]) -> tuple[str, dict[str, Any], None]:
    """Les images d'une colonne de liens (``column``) : ``{path, name, meta, g}`` - la légende (``caption``,
    les valeurs de quelques colonnes de la ligne) et le groupe (``group_by``). Au plus ``max`` images, prises
    tour à tour dans chaque groupe pour qu'aucun n'en manque ; ``counts`` : combien chaque groupe en a."""
    kept, day, days = select_rows(columns, rows, config.get("filters", []), config.get("date", "latest"))
    at = _at(columns, config["column"])
    captions = [(name, _at(columns, name)) for name in config.get("caption", [])]
    kept = [row for row in kept if isinstance(row[at], str) and row[at].strip()]
    base = {"date": day, "dates": days}
    if not kept:
        return "empty", {**base, "images": [], "total": 0}, None
    names, member = grouping(kept, _group_at(columns, config, "group_by"), limit=12)
    queues: list[list[int]] = [[] for _ in names]
    for i, g in enumerate(member):
        queues[g].append(i)
    chosen: list[int] = []
    limit = config.get("max", 60)
    while len(chosen) < limit and any(queues):
        for queue in queues:
            if queue and len(chosen) < limit:
                chosen.append(queue.pop(0))
    chosen.sort(key=lambda i: (member[i], i))
    found = []
    for i in chosen:
        path = kept[i][at].strip()
        found.append({"path": path, "name": os.path.basename(path.replace("\\", "/")), "meta": {name: label(kept[i][c]) for name, c in captions}, "g": member[i]})
    return "ok", {
        **base, "images": found, "total": len(kept), "groups": names if config.get("group_by") else [],
        "counts": [member.count(g) for g in range(len(names))],
    }, None


COMPUTE = {"value": value, "histogram": histogram, "boxplot": boxplot, "scatter": scatter, "wafermap": wafermap, "curve": curve, "images": images}
