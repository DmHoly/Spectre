"""Les blocs de la fiche data d'un projet corporate : ce que l'onglet « Data » de chacune de ses plaques montre.

Un bloc est l'un de sept genres (:data:`KINDS`), chacun lisant des colonnes d'un **type** donné
(:mod:`.columns` : scalaire, vecteur, lien vers une image...) - une colonne d'un autre type est refusée :

- ``value`` - une valeur : l'agrégat d'un scalaire par plaque (médiane, moyenne, min, max, écart type,
  nombre) ou la part vraie d'un booléen, située parmi les plaques du projet (``better`` : dans quel sens
  elle est meilleure) ;
- ``histogram`` - la distribution d'un scalaire sur les dispositifs de la plaque ;
- ``boxplot`` - une boîte à moustaches d'un scalaire, une par groupe (``group_by`` : une catégorie) ;
- ``scatter`` - un nuage de points, un scalaire contre un autre ;
- ``wafermap`` - une cartographie : le scalaire par position (``x``, ``y``, les colonnes « X » et « Y » du type) ;
- ``curve`` - des courbes : deux vecteurs (``x``, ``y``), une courbe par ligne (EQE en fonction de V) -
  leur médiane et leur enveloppe (``mode`` ``envelope``) ou chacune (``curves``) ;
- ``images`` - une galerie : une colonne de liens vers des images (``column``, l'EL pattern de PRISM), ou des
  fichiers cherchés d'après un modèle de chemin (``pattern``, sans type de données) où ``{lasermark}``,
  ``{lot}``, ``{run}`` et ``{fdl}`` prennent les valeurs de la plaque, ``*`` et ``?`` dans le nom de fichier.
  Toujours sous les dossiers autorisés des images externes (``SPECTRE_EXTERNAL_IMAGE_ROOTS``).

La couleur : ``color_by`` (une catégorie : une couleur par valeur - nom de device, capteur, booléen...) pour
l'histogramme, le nuage et les courbes, ``group_by`` pour la boîte et la galerie ; sinon ``color`` (1 à 8, la
palette catégorielle de la charte). Tous filtrent les lignes (même vocabulaire que les KPI suivis,
:func:`kpi_tracking.service.clean_filters`) et, quand le type est daté, ne gardent que la mesure la plus
récente (``date`` ``latest``, par défaut) ou toutes.

Un bloc peut aussi être **libre** (:data:`FREE_AREA`) : choisi ailleurs que dans la fiche d'un projet - dans une
analyse de plaques (plugin meta_analysis), qui garde sa config et le fait calculer par :func:`.service.gather`.

Le projet ne garde que ce choix ; ce qu'un bloc calcule sur une plaque se garde, résumé, dans :mod:`.store`,
sous la **signature** du bloc (:attr:`Block.sig`, son projet, son genre, son type et sa config - pas son nom) :
changer la config d'un bloc fait oublier ce qu'il avait calculé.
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
from . import columns as col_types
from . import store
from .digest import AGGREGATES, WAFER_COLUMNS

KINDS = {
    "value": "Valeur",
    "histogram": "Histogramme",
    "boxplot": "Boîte à moustaches",
    "scatter": "Nuage de points",
    "wafermap": "Cartographie",
    "curve": "Courbes",
    "images": "Images",
}
AGGREGATE_LABELS = {"median": "médiane", "mean": "moyenne", "min": "min", "max": "max", "std": "écart type", "count": "nombre", "share": "part vraie"}
CURVE_MODES = {"envelope": "médiane et enveloppe 10-90 %", "curves": "chaque courbe"}
COLORED = ("histogram", "boxplot", "scatter", "curve")  # ceux qui prennent une couleur
COLORS = 8  # --viz-1 à --viz-8
MAX_BLOCKS = 24
MAX_LABEL = 80
MAX_PATTERN = 500
MAX_IMAGES = 200  # d'une colonne de liens
MAX_PATTERN_IMAGES = 24  # d'un modèle de chemin (un dossier parcouru à chaque fois)
MAX_CAPTION = 3
PLACEHOLDERS = ("lasermark", "lot", "run", "fdl")
FREE_AREA = 0  # le « projet » d'un bloc libre, hors de toute fiche (une analyse de plaques : service.free_block)

TYPE_PHRASES = {
    "number": "un scalaire",
    "vector": "un vecteur",
    "matrix": "des vecteurs (un par point)",
    "image": "un lien vers une image",
    "flag": "un booléen",
    "category": "une catégorie",
    "date": "une date",
    "other": "d'un autre type",
}
ROLE_PHRASES = {
    "number": "il faut ici un scalaire (un nombre par ligne)",
    "aggregate": "il faut ici un scalaire ou un booléen",
    "vector": "il faut ici un vecteur (une série par ligne)",
    "image": "il faut ici un lien vers une image",
    "group": "pour colorer ou grouper, il faut une catégorie, un booléen, un scalaire ou une date",
    "caption": "elle ne se lit pas en légende d'image",
}


@dataclass(frozen=True)
class CatalogHook:
    """Un type de données qu'un bloc peut lire : par plaque, et par plaque seulement. Ses colonnes :
    ``{name, unit, description, type, sure, chosen, observed_type, guessed, example, declared, observed}`` -
    ``type`` est celui qui compte (choisi, sinon observé, sinon deviné ; ``None`` : inconnu), ``sure`` dit
    s'il est choisi ou observé : un type seulement deviné sur la fiche PRISM guide la page sans rien refuser."""

    hook: str
    title: str
    category: str
    columns: tuple[dict[str, Any], ...]
    x: str | None  # les colonnes de position, si le type en a : de quoi une cartographie
    y: str | None
    dated: bool
    representative: str | None = None  # la colonne qui résume le type (PRISM) : celle qu'un nouveau bloc propose
    observed_at: str | None = None  # la dernière fois qu'on a vu ses vraies colonnes

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c["name"] for c in self.columns)

    def column(self, name: str | None) -> dict[str, Any] | None:
        return next((c for c in self.columns if c["name"] == name), None)

    def type_of(self, name: str | None, *, sure: bool = False) -> str | None:
        """Le type d'une colonne ; ``sure`` : seulement s'il est choisi ou observé (``None`` sinon)."""
        found = self.column(name)
        return found["type"] if found and (found["sure"] or not sure) else None


def _split(declared: str) -> list[str]:
    return [name.strip() for name in declared.split(" / ") if name.strip()]


def _entry(data_type: Any, chosen: dict[tuple[str, str], str], seen: list[dict[str, Any]]) -> CatalogHook:
    declared: dict[str, dict[str, Any]] = {}
    first_row = dict(data_type.example_rows[0]) if data_type.example_rows else {}
    for column in (*data_type.raw_columns, *data_type.kpi_columns):
        description = str(column.get("description") or "")
        names = _split(str(column.get("name") or ""))
        # une fiche PRISM documente parfois plusieurs colonnes d'un trait (« path / exists ») avec leurs exemples
        # du même trait (« N:\...\d10r1_Class.tif / true ») : à chaque colonne le sien, sinon son exemple de ligne
        examples = _split(str(column.get("example"))) if isinstance(column.get("example"), str) and len(names) > 1 else []
        for i, name in enumerate(names):
            if name.lower() not in WAFER_COLUMNS and name not in declared:
                example = column.get("example") if len(names) == 1 else (examples[i] if len(examples) == len(names) else first_row.get(name))
                declared[name] = {
                    "unit": str(column.get("unit") or ""),
                    "description": description,
                    "guessed": col_types.from_example(example, description),
                    "example": "" if example is None else col_types.example_text(example),
                }
    observed = {c["name"]: c for c in seen if c["name"].lower() not in WAFER_COLUMNS}
    columns = []
    for name in [*observed, *(n for n in declared if n not in observed)]:
        doc, obs = declared.get(name, {}), observed.get(name)
        chosen_type = chosen.get((data_type.key, name))
        observed_type = obs["type"] if obs else None
        columns.append(
            {
                "name": name,
                "unit": doc.get("unit", ""),
                "description": doc.get("description", ""),
                "type": chosen_type or observed_type or doc.get("guessed"),
                "sure": bool(chosen_type or observed_type),
                "chosen": chosen_type,
                "observed_type": observed_type,
                "guessed": doc.get("guessed"),
                "example": (obs or {}).get("example") or doc.get("example", ""),
                "declared": name in declared,
                "observed": obs is not None,
            }
        )
    positional = {c["name"].lower(): c["name"] for c in columns if col_types.fits(c["type"], "number")}
    return CatalogHook(
        data_type.key,
        data_type.title,
        data_type.category,
        tuple(columns),
        positional.get("x"),
        positional.get("y"),
        any(c["type"] == "date" or "date" in c["name"].lower() for c in columns),
        data_type.representative_column if any(c["name"] == data_type.representative_column for c in columns) else None,
        max((c["observed_at"] for c in seen), default=None),
    )


def catalog(hook: str | None = None) -> list[CatalogHook]:
    """Les types de données PRISM par plaque et leurs colonnes typées (un seul si ``hook``)."""
    chosen = col_types.chosen_types(hook)
    seen = store.observed(hook)
    hooks = []
    for data_type in characterization.list_types(status="implemented", by_wafer=True):
        if tuple(data_type.parameters) != (characterization.WAFER_PARAMETER,) or (hook and data_type.key != hook):
            continue
        hooks.append(_entry(data_type, chosen, seen.get(data_type.key, [])))
    return hooks


def catalog_entry(hook: str) -> CatalogHook | None:
    return next(iter(catalog(hook)), None) if hook else None


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
    def from_pattern(self) -> bool:
        """Des images cherchées d'après un modèle de chemin (pas dans un type de données PRISM)."""
        return self.kind == "images" and not self.hook

    @property
    def title(self) -> str:
        if self.label:
            return self.label
        c = self.config
        if self.kind == "value":
            return f"{c['column']} ({AGGREGATE_LABELS.get(c.get('aggregate', 'median'), '')})"
        if self.kind in ("curve", "scatter"):
            return f"{c['y']} en fonction de {c['x']}"
        if self.kind == "boxplot" and c.get("group_by"):
            return f"{c['column']} par {c['group_by']}"
        if self.kind == "images":
            return "Images" if self.from_pattern else f"Images · {c['column']}"
        return c["column"]

    def unit(self, entry: CatalogHook | None) -> str:
        """L'unité de ce que le bloc montre (``entry`` : son type de données dans le catalogue)."""
        if self.kind == "images":
            return ""
        if self.kind == "value" and self.config.get("aggregate") in ("count", "share"):
            return "%" if self.config.get("aggregate") == "share" else ""
        found = entry.column(self.config.get("column") or self.config.get("y")) if entry else None
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


def _column(entry: CatalogHook, config: dict[str, Any], key: str, role: str, default: str | None = None, *, optional: bool = False) -> str | None:
    """La colonne ``config[key]`` : une colonne du type de données, d'un type qui convient à ``role``."""
    name = str(config.get(key) or default or "")
    if not name and optional:
        return None
    if name not in entry.names:
        raise InvalidInput(f"« {name or '?'} » n'est pas une colonne de « {entry.title} ».", code="unknown_column")
    kind = entry.type_of(name, sure=True)
    if not col_types.fits(kind, role):
        raise InvalidInput(
            f"« {name} » est {TYPE_PHRASES.get(kind, 'd’un autre type')} : {ROLE_PHRASES[role]}. "
            "Si son type est mal reconnu, corrigez-le dans « Colonnes et types ».",
            code="wrong_column_type",
        )
    return name


def _color(config: dict[str, Any]) -> int:
    try:
        color = int(config.get("color") or 1)
    except (TypeError, ValueError):
        color = 1
    return min(max(color, 1), COLORS)


def first_of(entry: CatalogHook, role: str) -> str | None:
    """La première colonne qui convient à ``role`` (de quoi une valeur par défaut)."""
    return next((c["name"] for c in entry.columns if c["type"] in col_types.ROLES[role]), None)


def clean_config(kind: str, hook: str, config: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Le type de données et la config d'un bloc, vérifiés et réduits à ce que son genre lit (422 sinon)."""
    config = dict(config or {})
    if kind not in KINDS:
        raise InvalidInput(f"Genre de bloc inconnu : {kind!r}.", code="unknown_kind")
    if kind == "images" and (config.get("source") == "pattern" or (not hook and config.get("pattern"))):
        return "", _clean_pattern(config)
    entry = catalog_entry(hook)
    if entry is None:
        raise InvalidInput(f"« {hook or '?'} » n'est pas un type de données PRISM par plaque.", code="unknown_hook")
    cleaned: dict[str, Any] = {}
    if kind in ("curve", "scatter"):
        role = "vector" if kind == "curve" else "number"
        cleaned["x"] = _column(entry, config, "x", role)
        cleaned["y"] = _column(entry, config, "y", role)
        cleaned["log_x"], cleaned["log_y"] = bool(config.get("log_x")), bool(config.get("log_y"))
    elif kind == "images":
        cleaned["column"] = _column(entry, config, "column", "image", first_of(entry, "image"))
        caption = config.get("caption") or []
        if not isinstance(caption, list) or len(caption) > MAX_CAPTION:
            raise InvalidInput(f"Une légende d'image lit {MAX_CAPTION} colonnes au plus.", code="invalid_caption")
        cleaned["caption"] = list(dict.fromkeys(_column(entry, {"c": c}, "c", "caption") for c in caption))
        try:
            limit = int(config.get("max") or 60)
        except (TypeError, ValueError):
            limit = 60
        cleaned["max"] = max(1, min(limit, MAX_IMAGES))
    else:
        cleaned["column"] = _column(entry, config, "column", "aggregate" if kind == "value" else "number")
    if kind == "value":
        aggregate = config.get("aggregate") or ("share" if entry.type_of(cleaned["column"]) == "flag" else "median")
        if aggregate not in AGGREGATES:
            raise InvalidInput(f"Agrégat inconnu : {aggregate!r}.", code="unknown_aggregate")
        if entry.type_of(cleaned["column"], sure=True) == "flag" and aggregate != "share":
            raise InvalidInput(f"« {cleaned['column']} » est un booléen : il se résume par sa part vraie.", code="invalid_aggregate")
        better = config.get("better") or ""
        if better not in ("", "high", "low"):
            raise InvalidInput("« better » vaut high, low ou rien.", code="invalid_better")
        cleaned["aggregate"], cleaned["better"] = aggregate, better
    if kind == "wafermap":
        if not (entry.x and entry.y) and not (config.get("x") and config.get("y")):
            raise InvalidInput(f"« {entry.title} » n'a pas de colonnes de position (X, Y) : pas de cartographie.", code="no_positions")
        cleaned["x"] = _column(entry, config, "x", "number", entry.x)
        cleaned["y"] = _column(entry, config, "y", "number", entry.y)
    if kind in ("boxplot", "images"):
        cleaned["group_by"] = _column(entry, config, "group_by", "group", optional=True)
    if kind in ("histogram", "scatter", "curve"):
        cleaned["color_by"] = _column(entry, config, "color_by", "group", optional=True)
    if kind == "boxplot":
        cleaned["log_y"] = bool(config.get("log_y"))
    if kind == "curve":
        mode = config.get("mode") or "envelope"
        if mode not in CURVE_MODES:
            raise InvalidInput("« mode » vaut envelope ou curves.", code="invalid_mode")
        cleaned["mode"] = mode
    if kind in COLORED:
        cleaned["color"] = _color(config)
    date = config.get("date") or "latest"
    if date not in ("latest", "all"):
        raise InvalidInput("« date » vaut latest ou all.", code="invalid_date")
    cleaned["date"] = date
    target = cleaned.get("column") or cleaned.get("y")
    filterable = CatalogKpi(hook=hook, column=target, hook_title=entry.title, filter_columns=entry.names)
    cleaned["filters"] = clean_filters(filterable, config.get("filters"))
    return hook, cleaned


def _clean_pattern(config: dict[str, Any]) -> dict[str, Any]:
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
    return {"pattern": pattern, "max": max(1, min(limit, MAX_PATTERN_IMAGES))}


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
