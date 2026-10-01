"""Jeux de données du cahier d'une expérience : ce qu'une requête PRISM (paquet
``prism-aledia-datahook``) a renvoyé pour un lot de plaques, **figé en instantané** - un fichier JSON
du µprojet (à côté de ses pièces jointes, voir :func:`spectre.core.microprojects.attachments_dir`).
Le cahier et le rapport se relisent ainsi tels qu'ils étaient, sans retaper la base à chaque
affichage ; « Actualiser » prend un nouvel instantané.

Pour rester léger, un instantané écarte les colonnes 2D (un spectre par point de balayage...) et
ramène chaque vecteur à :data:`MAX_VECTOR_POINTS` points - en gardant les vecteurs d'une même ligne
alignés (I, V et EQE sous-échantillonnés aux mêmes indices). Les colonnes et leur forme sont
celles que renvoie PRISM, rien n'est renommé : ce sont les composants de visualisation (côté page,
``js/dataviz/``) qui savent lire chaque type de données.

Données de démonstration : avec ``SPECTRE_DEMO_DATA=1`` (instance de démo sans accès aux bases),
les instantanés viennent de :mod:`spectre.core.demo_data` au lieu de PRISM, et le disent
(``source: "demo"``) - jamais par défaut, jamais en repli silencieux d'une base injoignable.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from . import microprojects

logger = logging.getLogger(__name__)

MAX_ROWS = 20000
MAX_VECTOR_POINTS = 150
SNAPSHOT_ID_RE = re.compile(r"^snap_[0-9a-f]{20}$")


class DataSourceError(Exception):
    """Une requête qui n'a pas pu aboutir - ``status_code`` dit pourquoi (400 configuration, 404
    type inconnu, 422 demande invalide, 502 base injoignable / requête en échec)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def demo_enabled() -> bool:
    return os.environ.get("SPECTRE_DEMO_DATA") == "1"


def json_safe(value: Any) -> Any:
    """Une cellule de DataFrame en quelque chose que ``json.dumps`` accepte, sans changer sa forme
    (NaN -> None, horodatage -> ISO, scalaire/vecteur numpy -> Python)."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return json_safe(value.tolist())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value


def available_sources() -> list[dict[str, Any]]:
    """Les types de données qu'un cahier peut charger : les requêtes PRISM implémentées."""
    try:
        import prism
    except ImportError:  # PRISM absent : rien à proposer
        return []
    sources = []
    for key in prism.list_hooks():
        try:
            hook = prism.load_hook(key)
        except Exception:  # une fiche mal formée ne doit pas casser la liste
            continue
        if hook.status != "implemented":
            continue
        sources.append(
            {
                "key": hook.key,
                "title": hook.title,
                "category": hook.category,
                "description": hook.description,
                "by_wafer": "wafer_names" in hook.parameters,
                "representative_column": hook.representative_column,
            }
        )
    return sources


def _run_prism(hook_key: str, wafers: list[str], refresh: bool) -> tuple[list[str], list[list[Any]]]:
    import prism

    try:
        hook = prism.load_hook(hook_key)
    except prism.HookNotFoundError as exc:
        raise DataSourceError(404, f"type de données inconnu : {hook_key}") from exc
    if hook.status != "implemented":
        raise DataSourceError(422, "ce type de données n'est pas encore disponible (fiche documentaire)")
    by_wafer = "wafer_names" in hook.parameters
    if by_wafer and not wafers:
        raise DataSourceError(422, "indiquez au moins une plaque (lasermark)")
    try:
        if hook.cache_key_column and by_wafer:
            df = prism.run_hook_cached(hook_key, wafer_names=wafers, refresh=refresh).df
        elif by_wafer:
            df = prism.run_hook(hook_key, wafer_names=wafers)
        else:
            df = prism.run_hook(hook_key)
    except prism.HookDefinitionError as exc:
        raise DataSourceError(400, str(exc)) from exc
    except prism.ConfigError as exc:
        raise DataSourceError(400, f"configuration de connexion PRISM incomplète : {exc}") from exc
    except Exception as exc:  # base injoignable, requête ou post-traitement en échec
        logger.warning("cahier : requête %r en échec (%s)", hook_key, exc)
        raise DataSourceError(502, f"la requête PRISM a échoué : {exc}") from exc
    columns = [str(c) for c in df.columns]
    rows = [[json_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return columns, rows


def _is_vector(value: Any) -> bool:
    return isinstance(value, list) and value and all(isinstance(v, (int, float)) or v is None for v in value)


def _is_matrix(value: Any) -> bool:
    return isinstance(value, list) and value and isinstance(value[0], list)


def _sample_indices(length: int, points: int) -> list[int]:
    return sorted({round(i * (length - 1) / (points - 1)) for i in range(points)})


def compact(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    """Le jeu de données tel qu'un instantané le garde : sans colonne 2D, vecteurs ramenés à
    :data:`MAX_VECTOR_POINTS` points (alignés ligne par ligne), au plus :data:`MAX_ROWS` lignes."""
    dropped = [i for i, _ in enumerate(columns) if any(_is_matrix(row[i]) for row in rows[:50])]
    keep = [i for i in range(len(columns)) if i not in dropped]
    truncated = len(rows) > MAX_ROWS
    out_rows = []
    for row in rows[:MAX_ROWS]:
        cells = [row[i] for i in keep]
        lengths = {len(c) for c in cells if _is_vector(c) and len(c) > MAX_VECTOR_POINTS}
        for length in lengths:
            idx = _sample_indices(length, MAX_VECTOR_POINTS)
            cells = [[c[j] for j in idx] if _is_vector(c) and len(c) == length else c for c in cells]
        out_rows.append(cells)
    return {
        "columns": [columns[i] for i in keep],
        "rows": out_rows,
        "dropped_columns": [columns[i] for i in dropped],
        "truncated": truncated,
    }


def fetch(hook_key: str, wafers: list[str], *, refresh: bool = False) -> dict[str, Any]:
    """Charge un jeu de données (PRISM, ou la démo si elle est activée) et le compacte."""
    wafers = [w.strip() for w in wafers if w and w.strip()][:50]
    if demo_enabled():
        from .demo_data import generate

        columns, rows = generate(hook_key, wafers)
        source = "demo"
        title = next((s["title"] for s in available_sources() if s["key"] == hook_key), hook_key)
    else:
        columns, rows = _run_prism(hook_key, wafers, refresh)
        source = "prism"
        title = next((s["title"] for s in available_sources() if s["key"] == hook_key), hook_key)
    return {
        "hook": hook_key,
        "hook_title": title,
        "wafers": wafers,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **compact(columns, rows),
    }


def store(slug: str, dataset: dict[str, Any]) -> str:
    snapshot_id = f"snap_{secrets.token_hex(10)}"
    path = microprojects.attachments_dir(slug) / f"{snapshot_id}.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return snapshot_id


def load(slug: str, snapshot_id: str) -> dict[str, Any]:
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id or ""):
        raise DataSourceError(404, "instantané introuvable")
    path = microprojects.attachments_dir(slug) / f"{snapshot_id}.json"
    if not path.is_file():
        raise DataSourceError(404, "instantané introuvable")
    return json.loads(path.read_text(encoding="utf-8"))


def exists(slug: str, snapshot_id: str) -> bool:
    return bool(SNAPSHOT_ID_RE.fullmatch(snapshot_id or "")) and (microprojects.attachments_dir(slug) / f"{snapshot_id}.json").is_file()
