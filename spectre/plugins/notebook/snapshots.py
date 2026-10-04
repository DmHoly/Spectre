"""Jeux de données du cahier d'une expérience : ce qu'une requête PRISM (paquet
``prism-aledia-datahook``) a renvoyé pour un lot de plaques, **figé en instantané** - un fichier JSON
du µprojet, dans son dossier ``snapshots/`` (les instantanés d'avant, rangés avec les pièces jointes,
restent lisibles : :func:`spectre.plugins.attachments.store.attachments_dir`). Un instantané ne change
jamais. Le cahier et le rapport se relisent ainsi tels qu'ils étaient, sans retaper la base à chaque
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
from pathlib import Path
from typing import Any

from ...kernel.errors import NotFound
from ..attachments.store import attachments_dir
from ..characterization import service as characterization
from ..microprojects.service import microproject_dir

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


def snapshots_dir(slug: str) -> Path:
    path = microproject_dir(slug) / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store(slug: str, dataset: dict[str, Any]) -> str:
    snapshot_id = f"snap_{secrets.token_hex(10)}"
    path = snapshots_dir(slug) / f"{snapshot_id}.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return snapshot_id


def _path(slug: str, snapshot_id: str) -> Path | None:
    """Le fichier de l'instantané : dans ``snapshots/``, ou parmi les pièces jointes pour un
    instantané d'avant ce dossier - ``None`` pour un id mal formé ou un instantané absent."""
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id or ""):
        return None
    for directory in (snapshots_dir(slug), attachments_dir(slug)):
        path = directory / f"{snapshot_id}.json"
        if path.is_file():
            return path
    return None


def load(slug: str, snapshot_id: str) -> dict[str, Any]:
    path = _path(slug, snapshot_id)
    if path is None:
        raise NotFound("instantané introuvable", code="snapshot_not_found")
    return json.loads(path.read_text(encoding="utf-8"))


def exists(slug: str, snapshot_id: str) -> bool:
    return _path(slug, snapshot_id) is not None


def summary(dataset: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'une mesure PRISM du cahier retient de son instantané, pour se décrire sans le relire :
    le type de données, les plaques chargées, la source, la date et le nombre de lignes."""
    return {
        "hook": dataset.get("hook"),
        "hook_title": dataset.get("hook_title"),
        "wafers": dataset.get("wafers", []),
        "source": dataset.get("source"),
        "fetched_at": dataset.get("fetched_at"),
        "row_count": len(dataset.get("rows", [])),
    }
