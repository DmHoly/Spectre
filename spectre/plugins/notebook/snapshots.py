"""Jeux de données du cahier d'une expérience : ce qu'une requête PRISM (paquet
``prism-aledia-datahook``) a renvoyé pour un lot de plaques, **figé en instantané** - un fichier JSON
du µprojet (à côté de ses pièces jointes, voir :func:`spectre.plugins.attachments.store.attachments_dir`).
Le cahier et le rapport se relisent ainsi tels qu'ils étaient, sans retaper la base à chaque
affichage ; « Actualiser » prend un nouvel instantané.

Pour rester léger, un instantané écarte les colonnes 2D (un spectre par point de balayage...) et
ramène chaque vecteur à :data:`MAX_VECTOR_POINTS` points - en gardant les vecteurs d'une même ligne
alignés (I, V et EQE sous-échantillonnés aux mêmes indices). Les colonnes et leur forme sont
celles que renvoie PRISM, rien n'est renommé : ce sont les composants de visualisation (côté page,
``notebook/static/dataviz/``) qui savent lire chaque type de données.

Données de démonstration : avec ``SPECTRE_DEMO_DATA=1`` (instance de démo sans accès aux bases),
les instantanés viennent de :mod:`spectre.plugins.characterization.demo` au lieu de PRISM, et le
disent (``source: "demo"``) - voir :func:`spectre.plugins.characterization.service.query`.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from ...kernel.errors import NotFound
from ..attachments.store import attachments_dir
from ..characterization import service as characterization

MAX_ROWS = 20000
MAX_VECTOR_POINTS = 150
SNAPSHOT_ID_RE = re.compile(r"^snap_[0-9a-f]{20}$")


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
    result = characterization.query(hook_key, {"wafer_names": wafers}, refresh=refresh)
    return {
        "hook": hook_key,
        "hook_title": characterization.describe(hook_key).title,
        "wafers": result.wafers,
        "source": result.source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **compact(result.columns, result.rows),
    }


def store(slug: str, dataset: dict[str, Any]) -> str:
    snapshot_id = f"snap_{secrets.token_hex(10)}"
    path = attachments_dir(slug) / f"{snapshot_id}.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return snapshot_id


def load(slug: str, snapshot_id: str) -> dict[str, Any]:
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id or ""):
        raise NotFound("instantané introuvable")
    path = attachments_dir(slug) / f"{snapshot_id}.json"
    if not path.is_file():
        raise NotFound("instantané introuvable")
    return json.loads(path.read_text(encoding="utf-8"))


def exists(slug: str, snapshot_id: str) -> bool:
    return bool(SNAPSHOT_ID_RE.fullmatch(snapshot_id or "")) and (attachments_dir(slug) / f"{snapshot_id}.json").is_file()
