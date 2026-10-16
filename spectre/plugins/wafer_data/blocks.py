"""Les blocs de la fiche data d'un projet corporate : ce que l'onglet « Data » de chacune de ses plaques montre.

Un bloc est l'un de cinq genres (:data:`KINDS`) :

- ``value`` - une valeur : l'agrégat d'une colonne d'un type de données PRISM par plaque (médiane, moyenne,
  min, max, écart type, nombre, part des lignes vraies), située parmi les plaques du projet (``better`` :
  dans quel sens elle est meilleure) ;
- ``histogram`` - la distribution d'une colonne sur les dispositifs de la plaque ;
- ``wafermap`` - une cartographie : la colonne par position (``x``, ``y``, les colonnes « X » et « Y » du type) ;
- ``curve`` - une courbe médiane et son enveloppe : deux colonnes vectorielles (``x``, ``y``), une courbe par ligne ;
- ``images`` - des fichiers cherchés d'après un modèle de chemin (``pattern``) où ``{lasermark}``, ``{lot}``,
  ``{run}`` et ``{fdl}`` prennent les valeurs de la plaque, ``*`` et ``?`` dans le nom de fichier - sous les
  dossiers autorisés des images externes (``SPECTRE_EXTERNAL_IMAGE_ROOTS``).

Tous peuvent filtrer les lignes (même vocabulaire que les KPI suivis, :func:`kpi_tracking.service.clean_filters`)
et, quand le type est daté, ne garder que la mesure la plus récente (``date`` ``latest``, par défaut) ou toutes.
Le projet ne garde que ce choix ; ce qu'un bloc calcule sur une plaque se garde, résumé, dans :mod:`.store`,
sous la **signature** du bloc (:attr:`Block.sig`, son projet, son genre, son type et sa config - pas son nom) : changer la
config d'un bloc fait oublier ce qu'il avait calculé.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput, NotFound
from ..accounts.service import User
from ..areas.service import ManagementArea
from ..characterization import service as characterization
from ..kpi_tracking.service import CatalogKpi, clean_filters
from . import store
from .digest import AGGREGATES, WAFER_COLUMNS

KINDS = {
    "value": "Valeur",
    "histogram": "Histogramme",
    "wafermap": "Cartographie",
    "curve": "Courbe",
    "images": "Images",
}
AGGREGATE_LABELS = {"median": "médiane", "mean": "moyenne", "min": "min", "max": "max", "std": "écart type", "count": "nombre", "share": "part vraie"}
MAX_BLOCKS = 24
MAX_LABEL = 80
MAX_PATTERN = 500
MAX_IMAGES = 24
PLACEHOLDERS = ("lasermark", "lot", "run", "fdl")


@dataclass(frozen=True)
class CatalogHook:
    """Un type de données qu'un bloc peut lire : par plaque, et par plaque seulement."""

    hook: str
    title: str
    category: str
    columns: tuple[dict[str, str], ...]  # {name, unit, description}
    x: str | None  # les colonnes de position, si le type en a : de quoi une cartographie
    y: str | None
    dated: bool
    representative: str | None = None  # la colonne qui résume le type (PRISM) : celle qu'un nouveau bloc propose

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c["name"] for c in self.columns)


def _split(declared: str) -> list[str]:
    return [name.strip() for name in declared.split(" / ") if name.strip()]


def catalog() -> list[CatalogHook]:
    hooks = []
    for data_type in characterization.list_types(status="implemented", by_wafer=True):
        if tuple(data_type.parameters) != (characterization.WAFER_PARAMETER,):
            continue
        columns: dict[str, dict[str, str]] = {}
        for column in (*data_type.raw_columns, *data_type.kpi_columns):
            for name in _split(str(column.get("name") or "")):
                if name.lower() not in WAFER_COLUMNS and name not in columns:
                    columns[name] = {"name": name, "unit": str(column.get("unit") or ""), "description": str(column.get("description") or "")}
        by_lower = {name.lower(): name for name in columns}
        hooks.append(
            CatalogHook(
                data_type.key, data_type.title, data_type.category, tuple(columns.values()),
                by_lower.get("x"), by_lower.get("y"), any("date" in name.lower() for name in columns),
                data_type.representative_column if data_type.representative_column in columns else None,
            )
        )
    return hooks


def catalog_entry(hook: str) -> CatalogHook | None:
    return next((h for h in catalog() if h.hook == hook), None)


@dataclass(frozen=True)
class Block:
    id: int
    area_id: int
    kind: str
    hook: str
    config: dict[str, Any]
    label: str
    position: int
    created_at: str

    @property
    def sig(self) -> str:
        return signature(self.area_id, self.kind, self.hook, self.config)

    @property
    def title(self) -> str:
        if self.label:
            return self.label
        c = self.config
        if self.kind == "value":
            return f"{c['column']} ({AGGREGATE_LABELS.get(c.get('aggregate', 'median'), '')})"
        if self.kind == "curve":
            return f"{c['y']} en fonction de {c['x']}"
        if self.kind == "images":
            return "Images"
        return c["column"]

    @property
    def unit(self) -> str:
        if self.kind == "images" or (self.kind == "value" and self.config.get("aggregate") in ("count", "share")):
            return "%" if self.config.get("aggregate") == "share" else ""
        entry = catalog_entry(self.hook)
        column = self.config.get("column") or self.config.get("y")
        found = next((c for c in entry.columns if c["name"] == column), None) if entry else None
        return found["unit"] if found else ""


def signature(area_id: int, kind: str, hook: str, config: dict[str, Any]) -> str:
    """Le projet en fait partie : une valeur se situe parmi les plaques de son projet, pas de tous ceux qui
    auraient choisi le même bloc."""
    text = json.dumps({"area": area_id, "kind": kind, "hook": hook, "config": config}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def _block(row) -> Block:
    return Block(row["id"], row["area_id"], row["kind"], row["hook"], json.loads(row["config"]), row["label"], row["position"], row["created_at"])


def list_blocks(area: ManagementArea) -> list[Block]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM area_wafer_sheet_blocks WHERE area_id = ? ORDER BY position, id", (area.id,)).fetchall()
    return [_block(r) for r in rows]


def blocks_by_area(area_ids: list[int]) -> dict[int, list[Block]]:
    if not area_ids:
        return {}
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM area_wafer_sheet_blocks WHERE area_id IN ({','.join('?' * len(area_ids))}) ORDER BY position, id", tuple(area_ids)
        ).fetchall()
    found: dict[int, list[Block]] = {}
    for row in rows:
        found.setdefault(row["area_id"], []).append(_block(row))
    return found


def _clean_label(label: str | None) -> str:
    label = " ".join((label or "").split())
    if len(label) > MAX_LABEL:
        raise InvalidInput(f"Un nom de bloc fait {MAX_LABEL} caractères au plus.", code="label_too_long")
    return label


def _column(entry: CatalogHook, config: dict[str, Any], key: str, default: str | None = None) -> str:
    name = str(config.get(key) or default or "")
    if name not in entry.names:
        raise InvalidInput(f"« {name or '?'} » n'est pas une colonne de « {entry.title} ».", code="unknown_column")
    return name


def clean_config(kind: str, hook: str, config: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Le type de données et la config d'un bloc, vérifiés et réduits à ce que son genre lit (422 sinon)."""
    config = dict(config or {})
    if kind not in KINDS:
        raise InvalidInput(f"Genre de bloc inconnu : {kind!r}.", code="unknown_kind")
    if kind == "images":
        return "", _clean_images(config)
    entry = catalog_entry(hook)
    if entry is None:
        raise InvalidInput(f"« {hook} » n'est pas un type de données PRISM par plaque.", code="unknown_hook")
    cleaned: dict[str, Any] = {}
    if kind == "curve":
        cleaned["x"] = _column(entry, config, "x")
        cleaned["y"] = _column(entry, config, "y")
        cleaned["log_x"] = bool(config.get("log_x"))
        cleaned["log_y"] = bool(config.get("log_y"))
    else:
        cleaned["column"] = _column(entry, config, "column")
    if kind == "value":
        aggregate = config.get("aggregate") or "median"
        if aggregate not in AGGREGATES:
            raise InvalidInput(f"Agrégat inconnu : {aggregate!r}.", code="unknown_aggregate")
        better = config.get("better") or ""
        if better not in ("", "high", "low"):
            raise InvalidInput("« better » vaut high, low ou rien.", code="invalid_better")
        cleaned["aggregate"], cleaned["better"] = aggregate, better
    if kind == "wafermap":
        if not (entry.x and entry.y) and not (config.get("x") and config.get("y")):
            raise InvalidInput(f"« {entry.title} » n'a pas de colonnes de position (X, Y) : pas de cartographie.", code="no_positions")
        cleaned["x"] = _column(entry, config, "x", entry.x)
        cleaned["y"] = _column(entry, config, "y", entry.y)
    date = config.get("date") or "latest"
    if date not in ("latest", "all"):
        raise InvalidInput("« date » vaut latest ou all.", code="invalid_date")
    cleaned["date"] = date
    target = cleaned.get("column") or cleaned.get("y")
    filterable = CatalogKpi(hook=hook, column=target, hook_title=entry.title, filter_columns=entry.names)
    cleaned["filters"] = clean_filters(filterable, config.get("filters"))
    return hook, cleaned


def _clean_images(config: dict[str, Any]) -> dict[str, Any]:
    pattern = str(config.get("pattern") or "").strip()
    if not pattern:
        raise InvalidInput("Indiquez où chercher les images (un modèle de chemin).", code="missing_pattern")
    if len(pattern) > MAX_PATTERN:
        raise InvalidInput(f"Un modèle de chemin fait {MAX_PATTERN} caractères au plus.", code="pattern_too_long")
    names = set(re.findall(r"\{([^{}]*)\}", pattern))
    unknown = names - set(PLACEHOLDERS)
    if unknown:
        raise InvalidInput(f"Repère inconnu : {{{sorted(unknown)[0]}}} (connus : {', '.join('{' + p + '}' for p in PLACEHOLDERS)}).", code="unknown_placeholder")
    if not names:
        raise InvalidInput("Le modèle doit nommer la plaque - {lasermark}, {lot}, {run} ou {fdl} - sinon toutes les plaques montreraient les mêmes images.", code="pattern_without_wafer")
    directory, _, name = pattern.replace("\\", "/").rpartition("/")
    if not directory or not name:
        raise InvalidInput("Le modèle est un chemin de fichier : un dossier, puis un nom (« *.png » pour toutes les images).", code="invalid_pattern")
    if any(c in directory for c in "*?["):
        raise InvalidInput("« * » et « ? » ne vont que dans le nom de fichier, pas dans le dossier.", code="invalid_pattern")
    try:
        limit = int(config.get("max") or 8)
    except (TypeError, ValueError):
        limit = 8
    return {"pattern": pattern, "max": max(1, min(limit, MAX_IMAGES))}


def add_block(area: ManagementArea, user: User, kind: str, hook: str, config: dict[str, Any] | None, label: str | None = None) -> Block:
    hook, cleaned = clean_config(kind, hook, config)
    label = _clean_label(label)
    with get_conn() as conn:
        count, last = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(position), -1) FROM area_wafer_sheet_blocks WHERE area_id = ?", (area.id,)
        ).fetchone()
        if count >= MAX_BLOCKS:
            raise InvalidInput(f"{MAX_BLOCKS} blocs au plus par fiche.", code="too_many_blocks")
        cursor = conn.execute(
            "INSERT INTO area_wafer_sheet_blocks (area_id, kind, hook, config, label, position, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (area.id, kind, hook, json.dumps(cleaned, ensure_ascii=False), label, last + 1, user.id),
        )
        row = conn.execute("SELECT * FROM area_wafer_sheet_blocks WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _block(row)


def _get(conn, area: ManagementArea, block_id: int):
    row = conn.execute("SELECT * FROM area_wafer_sheet_blocks WHERE id = ? AND area_id = ?", (block_id, area.id)).fetchone()
    if row is None:
        raise NotFound("Bloc inconnu pour ce projet.")
    return row


def get_block(area: ManagementArea, block_id: int) -> Block:
    with get_conn() as conn:
        return _block(_get(conn, area, block_id))


def update_block(
    area: ManagementArea, block_id: int, *, label: str | None = None, config: dict[str, Any] | None = None, move: str | None = None
) -> Block:
    """Renomme un bloc, remplace sa config (même genre, même type de données : ce qu'il avait calculé est
    oublié) ou le déplace d'un cran (``move`` ``up`` / ``down``)."""
    forget = None
    with get_conn() as conn:
        block = _block(_get(conn, area, block_id))
        if label is not None:
            conn.execute("UPDATE area_wafer_sheet_blocks SET label = ? WHERE id = ?", (_clean_label(label), block_id))
        if config is not None:
            _, cleaned = clean_config(block.kind, block.hook, config)
            if cleaned != block.config:
                conn.execute("UPDATE area_wafer_sheet_blocks SET config = ? WHERE id = ?", (json.dumps(cleaned, ensure_ascii=False), block_id))
                forget = block.sig
        if move in ("up", "down"):
            order = [r["id"] for r in conn.execute("SELECT id FROM area_wafer_sheet_blocks WHERE area_id = ? ORDER BY position, id", (area.id,))]
            at = order.index(block_id)
            other = at - 1 if move == "up" else at + 1
            if 0 <= other < len(order):
                order[at], order[other] = order[other], order[at]
                conn.executemany("UPDATE area_wafer_sheet_blocks SET position = ? WHERE id = ?", [(i, bid) for i, bid in enumerate(order)])
        elif move is not None:
            raise InvalidInput("« move » vaut up ou down.", code="invalid_move")
        row = _get(conn, area, block_id)
    if forget:
        store.forget(forget)
    return _block(row)


def remove_block(area: ManagementArea, block_id: int) -> None:
    with get_conn() as conn:
        block = _block(_get(conn, area, block_id))
        conn.execute("DELETE FROM area_wafer_sheet_blocks WHERE id = ?", (block_id,))
    store.forget(block.sig)
