"""Le type des colonnes d'un type de données PRISM : ce qu'une colonne porte, donc ce qu'un bloc peut en faire.

PRISM documente ses colonnes (``hook.yml`` : nom, description, unité, exemple) sans dire ce qu'elles
contiennent - et une requête rend souvent plus de colonnes que la fiche n'en documente. Le type d'une
colonne se décide donc, du plus sûr au moins sûr :

1. **choisi** sur la page « Fiche data » (:func:`set_type`, table ``wafer_data_column_types``) - vaut pour
   tous les projets : c'est une propriété de la donnée, pas d'un projet ;
2. **observé** sur de vraies lignes : chaque lecture d'un type de données pour une fiche en garde le profil
   (:func:`profile`, magasin :mod:`.store`) - les colonnes réellement rendues, leur type, un exemple ;
3. **deviné** sur l'exemple de la fiche PRISM (:func:`from_example`), faute de mieux.

Les types (:data:`TYPES`) : un scalaire (un nombre par ligne), un vecteur (le balayage d'un device : I, V,
EQE...), des vecteurs (un spectre par point du balayage), un lien vers une image (un chemin de fichier), un
booléen, une catégorie (un texte : nom de device, capteur, run), une date, autre chose.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput

TYPES = {
    "number": "Scalaire",
    "vector": "Vecteur",
    "matrix": "Vecteurs (un par point)",
    "image": "Lien vers une image",
    "flag": "Booléen",
    "category": "Catégorie",
    "date": "Date",
    "other": "Autre",
}

# Ce que chaque usage d'une colonne accepte. Une colonne au type inconnu (ni choisi, ni observé, ni devinable)
# est acceptée partout : mieux vaut un bloc qui dit « pas de mesure » qu'un refus sans raison.
ROLES = {
    "number": ("number",),  # histogramme, boîte, nuage, cartographie
    "aggregate": ("number", "flag"),  # une valeur : un agrégat, ou la part vraie d'un booléen
    "vector": ("vector",),  # les axes d'une courbe
    "image": ("image",),  # une galerie
    "group": ("category", "flag", "number", "date"),  # couleur, groupes d'une boîte
    "caption": ("category", "flag", "number", "date", "other"),  # la légende d'une image
}

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")
SAMPLE_ROWS = 200
MAX_EXAMPLE = 60
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cell_type(value: Any) -> str | None:
    """Le type d'une cellule telle que la source la rend (après :func:`json_safe` : un NaN est ``None``) ;
    ``None`` pour une cellule vide, qui ne dit rien."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "flag"
    if _is_number(value):
        return "number" if not isinstance(value, float) or math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        items = [v for v in value if v is not None]
        if not items:
            return None
        if all(isinstance(v, (list, tuple)) for v in items):
            return "matrix"
        if all(_is_number(v) for v in items):
            return "vector"
        return "other"
    if isinstance(value, dict):
        return "other"
    text = str(value).strip()
    if not text:
        return None
    if text.lower().endswith(IMAGE_SUFFIXES):
        return "image"
    if _DATE.match(text):
        return "date"
    return "category"


def infer(values: list[Any]) -> str | None:
    """Le type d'une colonne : celui de la plupart de ses cellules non vides."""
    found = Counter(t for v in values if (t := cell_type(v)) is not None)
    return found.most_common(1)[0][0] if found else None


def example_text(value: Any) -> str:
    """Un exemple court, lisible dans une liste de colonnes : « 21 valeurs : 0,0012 … 0,018 » pour un vecteur."""
    if isinstance(value, (list, tuple)):
        items = [v for v in value if v is not None]
        if items and all(_is_number(v) for v in items):
            return f"{len(value)} valeurs : {items[0]:.4g} … {items[-1]:.4g}"
        if items and all(isinstance(v, (list, tuple)) for v in items):
            return f"{len(value)} × {len(items[0])} valeurs"
        return f"{len(value)} éléments"
    if isinstance(value, float):
        return f"{value:.4g}"
    text = str(value)
    return text if len(text) <= MAX_EXAMPLE else f"…{text[-(MAX_EXAMPLE - 1):]}"


def profile(columns: list[str], rows: list[list[Any]]) -> list[tuple[str, str | None, str]]:
    """Le profil des colonnes d'une réponse, sur ses :data:`SAMPLE_ROWS` premières lignes : ``(nom, type,
    exemple)`` dans l'ordre de la réponse."""
    sample = rows[:SAMPLE_ROWS]
    out = []
    for at, name in enumerate(columns):
        values = [row[at] for row in sample if at < len(row)]
        kind = infer(values)
        example = next((v for v in values if cell_type(v) == kind), None) if kind else None
        out.append((name, kind, example_text(example) if example is not None else ""))
    return out


def from_example(example: Any, description: str = "") -> str | None:
    """Le type deviné sur la fiche PRISM : son exemple (souvent écrit en texte - « [0.01, 0.05] » pour un
    vecteur), ou sa description qui dit « vecteur »."""
    if isinstance(example, str):
        text = example.strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if inner.startswith("["):
                return "matrix"
            parts = [p.strip() for p in inner.split(",") if p.strip()]
            return "vector" if parts and all(_NUMBER.match(p) for p in parts) else "other"
        if text.lower() in ("true", "false"):
            return "flag"
        if _NUMBER.match(text):
            return "number"
    kind = cell_type(example)
    if kind in (None, "category") and re.search(r"\bvecteurs?\b|\bvector\b", description, re.IGNORECASE):
        return "vector"
    return kind


# --- les types choisis ----------------------------------------------------------------------------


def chosen_types(hook: str | None = None) -> dict[tuple[str, str], str]:
    """Les types choisis à la main : ``{(type de données, colonne): type}``."""
    with get_conn() as conn:
        if hook is None:
            rows = conn.execute("SELECT hook, column_name, type FROM wafer_data_column_types").fetchall()
        else:
            rows = conn.execute("SELECT hook, column_name, type FROM wafer_data_column_types WHERE hook = ?", (hook,)).fetchall()
    return {(r["hook"], r["column_name"]): r["type"] for r in rows}


def set_type(hook: str, column: str, kind: str | None, user_id: int) -> None:
    """Choisit le type d'une colonne (``None`` : revenir au type observé ou deviné)."""
    if kind is None:
        with get_conn() as conn:
            conn.execute("DELETE FROM wafer_data_column_types WHERE hook = ? AND column_name = ?", (hook, column))
        return
    if kind not in TYPES:
        raise InvalidInput(f"Type de colonne inconnu : {kind!r} (connus : {', '.join(TYPES)}).", code="unknown_column_type")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wafer_data_column_types (hook, column_name, type, updated_by) VALUES (?, ?, ?, ?)
               ON CONFLICT (hook, column_name) DO UPDATE SET type = excluded.type, updated_by = excluded.updated_by,
               updated_at = datetime('now')""",
            (hook, column, kind, user_id),
        )


def fits(kind: str | None, role: str) -> bool:
    return kind is None or kind in ROLES[role]
