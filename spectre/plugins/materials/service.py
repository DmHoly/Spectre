"""Éditer ``materiaux.yml`` depuis une interface : le document que la page manipule (les matériaux du
sélecteur et les dégradés de couleur de l'InGaN et de l'AlGaN), validé, puis réécrit dans le fichier
par la bibliothèque racine (:func:`spectre.plugins.library.service.save`, qui le fait relire par
l'interprète du fichier avant de l'écrire).

Le sens du fichier reste à ``structures`` (:mod:`spectre.plugins.structures.library_files`) ; ici, rien
que sa mise en forme : l'en-tête de commentaires du fichier est gardé tel quel (il documente le format),
la liste et les dégradés sont réécrits - les commentaires qui les accompagnaient ne survivent pas, le
champ ``notes`` d'un matériau est fait pour ça.

Une page ouverte depuis un moment ne doit pas écraser une modification faite entre-temps (par un autre
administrateur, ou à la main dans le dossier de la bibliothèque) : le document porte la ``revision`` du
fichier qu'il décrit, et un enregistrement qui en cite une autre est refusé (409).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import yaml

from ...kernel.errors import Conflict, InvalidInput
from ...kernel.locks import keyed_lock
from ..library import service as library
from ..structures import library_files
from ..structures.library_files import GRADIENT_FAMILIES, HEX_COLOR_RE, Gradient

FILE_KEY = "materials"

CATEGORY_LABELS = {
    "substrate": "Substrats",
    "semiconductor": "Semi-conducteurs",
    "dielectric": "Diélectriques",
    "metal": "Métaux / TCO",
    "resist": "Résines",
    "other": "Autres",
}

_FIELDS = ("name", "category", "color", "density_g_cm3", "refractive_index", "notes")
_MAX_NAME, _MAX_NOTES = 64, 500
GRADED_NAME_RE = re.compile(r"^(In|Al)\d\.\d{2}Ga\d\.\d{2}N$")

def _text() -> str | None:
    return library.read_text(library.get_library_file(FILE_KEY))


def _revision(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


# -- lecture ---------------------------------------------------------------------------------------


def _material_dict(material: Any) -> dict[str, Any]:
    return {
        "name": material.name,
        "category": material.category.value if hasattr(material.category, "value") else str(material.category),
        "color": material.color,
        "density_g_cm3": material.density_g_cm3,
        "refractive_index": material.refractive_index,
        "notes": material.notes,
    }


def _gradient_dict(gradient: Gradient) -> dict[str, Any]:
    return {"stops": [{"x": x, "color": color} for x, color in gradient.stops], "generic_x": gradient.generic_x}


def read_document() -> dict[str, Any]:
    """Ce que la page édite : les matériaux et les dégradés du fichier, sa ``revision``, et de quoi
    remplir le formulaire (catégories, matériaux de StructureForge pas encore dans la liste, dégradés
    intégrés). Un fichier invalide - ``problem`` dit pourquoi - est montré par son jeu intégré de repli,
    celui que l'application utilise : l'enregistrer le répare."""
    file = library.get_library_file(FILE_KEY)
    text = _text()
    problem = None
    try:
        content = library.parse_text(file, text) if text is not None else file.fallback()
    except ValueError as exc:
        problem, content = str(exc), file.fallback()
    listed = {material.name for material in content.materials}
    offered = [
        _material_dict(material)
        for material in library_files.known_materials()
        if material.name not in listed and material.name not in GRADIENT_FAMILIES
    ]
    return {
        "revision": _revision(text),
        "exists": text is not None,
        "problem": problem,
        "categories": [{"value": value, "label": label} for value, label in CATEGORY_LABELS.items()],
        "materials": [_material_dict(material) for material in content.materials],
        "gradients": {family: _gradient_dict(gradient) for family, gradient in content.gradients.items()},
        "defaults": {family: _gradient_dict(gradient) for family, gradient in library_files.builtin_gradients().items()},
        "available": offered,
    }


# -- validation ------------------------------------------------------------------------------------


def _number(value: Any, label: str, *, minimum: float, maximum: float | None = None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInput(f"{label} : un nombre est attendu, reçu {value!r}.")
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"entre {minimum:g} et {maximum:g}" if maximum is not None else f"supérieur à {minimum:g}"
        raise InvalidInput(f"{label} : une valeur {bounds} est attendue, reçu {value:g}.")
    return float(value)


def _color(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX_COLOR_RE.match(value):
        raise InvalidInput(f'{label} : une couleur "#rrggbb" est attendue, reçu {value!r}.')
    return value.lower()


def _clean_materials(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise InvalidInput("La liste des matériaux ne peut pas être vide : le sélecteur du constructeur n'aurait rien à proposer.")
    categories = set(library_files.MATERIAL_CATEGORIES)
    seen: dict[str, str] = {}
    cleaned = []
    for i, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise InvalidInput(f"Matériau {i} : un objet est attendu.")
        name = str(entry.get("name") or "").strip()
        label = f"Matériau « {name} »" if name else f"Matériau {i}"
        if not name:
            raise InvalidInput(f"{label} : le nom est obligatoire.")
        if len(name) > _MAX_NAME or any(char in name for char in "\n\r\t"):
            raise InvalidInput(f"{label} : un nom d'une ligne de {_MAX_NAME} caractères au plus est attendu.")
        if name in GRADIENT_FAMILIES or GRADED_NAME_RE.match(name):
            raise InvalidInput(
                f"{label} : les nitrures à composition (InGaN, AlGaN) ne se listent pas ici - "
                "le constructeur les propose avec un taux, et leur couleur se règle dans les dégradés."
            )
        if name.casefold() in seen:
            raise InvalidInput(f"{label} : déjà présent (« {seen[name.casefold()]} ») - un nom ne se donne qu'une fois, sans distinguer majuscules et minuscules.")
        seen[name.casefold()] = name
        category = entry.get("category") or "other"
        if category not in categories:
            raise InvalidInput(f"{label} : catégorie inconnue {category!r} (attendu : {', '.join(sorted(categories))}).")
        notes = " ".join(str(entry.get("notes") or "").split())
        if len(notes) > _MAX_NOTES:
            raise InvalidInput(f"{label} : une description de {_MAX_NOTES} caractères au plus est attendue.")
        cleaned.append(
            {
                "name": name,
                "category": category,
                "color": _color(entry.get("color"), f"{label}, couleur"),
                "density_g_cm3": _number(entry.get("density_g_cm3"), f"{label}, densité", minimum=0.0),
                "refractive_index": _number(entry.get("refractive_index"), f"{label}, indice de réfraction", minimum=0.0),
                "notes": notes or None,
            }
        )
    return cleaned


def _clean_gradients(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or set(raw) != set(GRADIENT_FAMILIES):
        raise InvalidInput(f"Les dégradés des deux familles ({', '.join(GRADIENT_FAMILIES)}) sont attendus.")
    cleaned = {}
    for family in GRADIENT_FAMILIES:
        entry, label = raw[family], f"Dégradé {family}"
        stops_raw = entry.get("stops") if isinstance(entry, dict) else None
        if not isinstance(stops_raw, list) or len(stops_raw) < 2:
            raise InvalidInput(f"{label} : au moins deux couleurs sont nécessaires pour faire un dégradé.")
        stops = []
        for i, stop in enumerate(stops_raw, start=1):
            if not isinstance(stop, dict):
                raise InvalidInput(f"{label}, point {i} : un objet est attendu.")
            x = _number(stop.get("x"), f"{label}, point {i}, taux", minimum=0.0, maximum=1.0)
            if x is None:
                raise InvalidInput(f"{label}, point {i} : le taux est obligatoire.")
            stops.append({"x": round(x, 4), "color": _color(stop.get("color"), f"{label}, point {i}")})
        stops.sort(key=lambda stop: stop["x"])
        generic = _number(entry.get("generic_x"), f"{label}, taux du nom nu", minimum=0.0, maximum=1.0)
        cleaned[family] = {"stops": stops, "generic_x": round(generic if generic is not None else 0.0, 4)}
    return cleaned


# -- écriture --------------------------------------------------------------------------------------


def _header(text: str | None) -> str:
    """Les commentaires de tête du fichier (jusqu'à sa première clé) - ceux du fichier livré si le
    fichier n'existe pas encore."""
    if text is None:
        text = (library.DEFAULTS_DIR / "materiaux.yml").read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line and not line.startswith("#"):
            break
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


def _scalar(value: Any) -> str:
    """Une valeur YAML : une chaîne sans guillemets quand elle se relit telle quelle, entre guillemets sinon."""
    if isinstance(value, str):
        if value == value.strip() and not re.search(r"[:#\"'{}\[\],&*!|>%@`\\]", value):
            try:
                if yaml.safe_load(f"v: {value}") == {"v": value}:
                    return value
            except yaml.YAMLError:
                pass
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def _quoted(value: str) -> str:
    return json.dumps(value)


def render(header: str, materials: list[dict[str, Any]], gradients: dict[str, dict[str, Any]]) -> str:
    out = [header, "", "materials:"]
    previous = None
    for material in materials:
        if material["category"] != previous:
            out.append(f"  # -- {CATEGORY_LABELS.get(material['category'], material['category']).lower()} " + "-" * 40)
            previous = material["category"]
        first = True
        for field in _FIELDS:
            value = material[field]
            if value is None:
                continue
            text = _quoted(value) if field == "color" else _scalar(value)
            out.append(f"  {'- ' if first else '  '}{field}: {text}")
            first = False
    out += ["", "gradients:"]
    for family in GRADIENT_FAMILIES:
        gradient = gradients[family]
        out.append(f"  {family}:")
        out.append(f"    generic_x: {gradient['generic_x']!r}")
        out.append("    stops:")
        out += [f"      - {{ x: {stop['x']!r}, color: {_quoted(stop['color'])} }}" for stop in gradient["stops"]]
    return "\n".join(out) + "\n"


def save_document(document: Any) -> dict[str, Any]:
    """Valide ``document`` (les matériaux, les dégradés et la ``revision`` lue avec) et l'écrit dans
    ``materiaux.yml`` ; le document relu. ``InvalidInput`` dit quoi corriger, ``Conflict`` : le fichier
    a changé depuis la lecture."""
    if not isinstance(document, dict):
        raise InvalidInput("Un document (matériaux, dégradés, révision) est attendu.")
    materials = _clean_materials(document.get("materials"))
    gradients = _clean_gradients(document.get("gradients"))
    with keyed_lock("library", "materials-editor"):
        text = _text()
        if document.get("revision") != _revision(text):
            raise Conflict(
                "Le fichier des matériaux a changé depuis que cette page l'a lu (un autre administrateur, "
                "ou une édition à la main) : rechargez la page pour repartir de sa version actuelle.",
                code="library_file_changed",
            )
        library.save(FILE_KEY, render(_header(text), materials, gradients))
    return read_document()
