"""Les fichiers de la bibliothèque racine que possède ce plugin (``materiaux.yml``,
``recettes.yml``), déclarés au registre de ``library`` avec leur interprétation et leur repli.

``materiaux.yml`` porte deux choses : la liste du sélecteur (``materials``) et, pour les nitrures
à composition, le dégradé de couleur qui fait de la couleur d'un ``In0.20Ga0.80N`` ou d'un
``Al0.15Ga0.85N`` une fonction de son taux (``gradients``, voir :class:`Gradient`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, NamedTuple

from structureforge.core.materials import Material, MaterialCategory, default_library
from structureforge.core.recipes import DepositionRecipe, EtchRecipe

from ..library.service import LibraryFile, load, parse_entries, register_library_file


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Les familles de nitrures à composition : le nom nu du matériau (« InGaN ») et le symbole de l'élément
# dont le taux fait varier la couleur (In{x}Ga{1-x}N, Al{y}Ga{1-y}N).
GRADIENT_FAMILIES = {"InGaN": "In", "AlGaN": "Al"}


@dataclass(frozen=True)
class Gradient:
    """La couleur d'un nitrure à composition selon son taux ``x`` (de 0, le GaN pur, à 1) : un mélange
    linéaire, canal par canal, entre les deux ``stops`` qui encadrent le taux - ``(taux, "#rrggbb")``
    par taux croissant -, la première ou la dernière couleur au-delà. ``generic_x`` : le taux dont la
    couleur est celle du nom nu (« InGaN » sans taux)."""

    stops: tuple[tuple[float, str], ...]
    generic_x: float

    def color_at(self, x: float) -> str:
        x = min(max(x, 0.0), 1.0)
        first, last = self.stops[0], self.stops[-1]
        if x <= first[0]:
            return first[1]
        if x >= last[0]:
            return last[1]
        for (x0, c0), (x1, c1) in zip(self.stops, self.stops[1:]):
            if x0 <= x <= x1:
                return _blend(c0, c1, (x - x0) / (x1 - x0) if x1 > x0 else 0.0)
        return last[1]  # pragma: no cover - x est entre le premier et le dernier taux

    @property
    def generic_color(self) -> str:
        return self.color_at(self.generic_x)


def _blend(color_a: str, color_b: str, t: float) -> str:
    a, b = color_a.lstrip("#"), color_b.lstrip("#")
    channels = (round(int(a[i : i + 2], 16) + (int(b[i : i + 2], 16) - int(a[i : i + 2], 16)) * t) for i in (0, 2, 4))
    return "#" + "".join(f"{c:02x}" for c in channels)


class MaterialsFile(NamedTuple):
    """Le contenu interprété de ``materiaux.yml``."""

    materials: list[Material]
    gradients: dict[str, Gradient]  # par famille (« InGaN », « AlGaN ») : toujours les deux


def materials() -> list[Material]:
    """Les matériaux proposés dans le sélecteur du constructeur, dans l'ordre du fichier (il pilote
    l'ordre du menu). La simulation, elle, résout toujours n'importe quel nom connu de StructureForge."""
    return load("materials").materials


MATERIAL_CATEGORIES = tuple(category.value for category in MaterialCategory)


def builtin_gradients() -> dict[str, Gradient]:
    """Les dégradés intégrés : ceux du fichier livré, et le repli d'une famille absente du fichier."""
    return dict(_BUILTIN_GRADIENTS)


def known_materials() -> list[Material]:
    """Les matériaux que StructureForge connaît d'emblée : la simulation les résout tous, la liste du
    sélecteur n'en montre qu'une partie."""
    return list(default_library())


def gradient(family: str) -> Gradient:
    """Le dégradé de couleur de la famille ``family`` (« InGaN » ou « AlGaN »)."""
    return load("materials").gradients[family]


def recipes() -> tuple[list[DepositionRecipe], list[EtchRecipe]]:
    """Les recettes de dépôt et de gravure *en plus* de celles de StructureForge - c'est ici, et pas
    dans un préset, que vit une gravure sélective."""
    return load("recipes")


def _material_from_entry(entry: dict[str, Any]) -> Material:
    category = entry.get("category", "other")
    if category not in {c.value for c in MaterialCategory}:
        raise ValueError(f"catégorie de matériau inconnue : {category!r}")
    fields = {"name": entry["name"], "category": category}
    for optional in ("color", "density_g_cm3", "refractive_index", "notes"):
        if entry.get(optional) is not None:
            fields[optional] = entry[optional]
    return Material(**fields)


def _parse_gradient(family: str, raw: Any) -> Gradient:
    if not isinstance(raw, dict):
        raise ValueError(f"gradients.{family} invalide : attendu un mapping avec 'stops'")
    stops_raw = raw.get("stops")
    if not isinstance(stops_raw, list) or len(stops_raw) < 2:
        raise ValueError(f"gradients.{family}.stops : au moins deux couleurs (taux x et color) sont attendues")
    stops: list[tuple[float, str]] = []
    for i, stop in enumerate(stops_raw):
        if not isinstance(stop, dict) or "x" not in stop or "color" not in stop:
            raise ValueError(f"gradients.{family}.stops[{i}] invalide : 'x' (taux de 0 à 1) et 'color' sont obligatoires")
        x, color = stop["x"], stop["color"]
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 <= x <= 1:
            raise ValueError(f"gradients.{family}.stops[{i}].x : un taux entre 0 et 1, reçu {x!r}")
        if not isinstance(color, str) or not HEX_COLOR_RE.match(color):
            raise ValueError(f'gradients.{family}.stops[{i}].color : une couleur "#rrggbb", reçu {color!r}')
        stops.append((float(x), color.lower()))
    stops.sort(key=lambda stop: stop[0])
    generic_x = raw.get("generic_x", _BUILTIN_GRADIENTS[family].generic_x)
    if isinstance(generic_x, bool) or not isinstance(generic_x, (int, float)) or not 0 <= generic_x <= 1:
        raise ValueError(f"gradients.{family}.generic_x : un taux entre 0 et 1, reçu {generic_x!r}")
    return Gradient(tuple(stops), float(generic_x))


def _parse_materials_file(data: dict[str, Any]) -> MaterialsFile:
    materials = parse_entries(data, "materials", _material_from_entry)
    raw = data.get("gradients") or {}
    if not isinstance(raw, dict):
        raise ValueError("gradients : attendu un mapping (InGaN, AlGaN)")
    unknown = sorted(set(raw) - set(GRADIENT_FAMILIES))
    if unknown:
        raise ValueError(f"gradients : famille inconnue {unknown[0]!r} (attendu : {', '.join(GRADIENT_FAMILIES)})")
    # une famille absente garde son dégradé intégré : un fichier d'avant les dégradés reste valide
    gradients = {
        family: _parse_gradient(family, raw[family]) if family in raw else _BUILTIN_GRADIENTS[family]
        for family in GRADIENT_FAMILIES
    }
    return MaterialsFile(materials, gradients)


def _drop_none(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if v is not None}


def _parse_recipes(data: dict[str, Any]) -> tuple[list[DepositionRecipe], list[EtchRecipe]]:
    deposition = parse_entries(data, "deposition", lambda e: DepositionRecipe(**_drop_none(e)), required=False)
    etch = parse_entries(data, "etch", lambda e: EtchRecipe(**_drop_none(e)), required=False)
    return deposition, etch


# Le dégradé de l'InGaN balaie le spectre visible, comme l'émission réelle : de plus en plus d'indium
# décale le gap du violet (GaN pur, proche UV) au rouge, comprimé dans x de 0 à 0,5 (les LED
# violettes / bleues / vertes sont sous x ~ 0,3, les rouges vers 0,4-0,5), puis noir au-delà
# (proche infrarouge, hors du visible). Les stops vont dans l'ordre des longueurs d'onde. L'AlGaN, en
# rose / magenta : StructureForge le fond entre le violet-gris du GaN et le violet pâle de l'AlN,
# impossible à distinguer du GaN à 10-20 % d'Al ; le magenta est la seule teinte que ni le GaN ni
# l'arc-en-ciel de l'InGaN n'utilisent, et plus d'aluminium = plus pâle.
_BUILTIN_GRADIENTS: dict[str, Gradient] = {
    "InGaN": Gradient(
        (
            (0.00, "#4b0082"),
            (0.05, "#0033cc"),
            (0.10, "#00b4d8"),
            (0.16, "#2ecc71"),
            (0.22, "#f1c40f"),
            (0.28, "#e67e22"),
            (0.35, "#e63946"),
            (0.50, "#2a0a0a"),
            (1.00, "#000000"),
        ),
        generic_x=0.15,
    ),
    "AlGaN": Gradient(((0.0, "#d01c8b"), (1.0, "#f6c8e0")), generic_x=0.3),
}


def _builtin_materials_file() -> MaterialsFile:
    return MaterialsFile(_builtin_materials(), dict(_BUILTIN_GRADIENTS))


def _builtin_materials() -> list[Material]:
    """Repli quand ``materiaux.yml`` est absent : une liste resserrée orientée nitrures /
    semi-conducteurs (mêmes couleurs que la bibliothèque StructureForge d'origine), plus deux oxydes
    conducteurs / alliages absents de StructureForge (GZO, AlCu). Le fichier livré reprend cette liste.
    """
    m = MaterialCategory
    entries: list[tuple[str, MaterialCategory, str]] = [
        ("Si", m.substrate, "#5b5f66"),
        ("Sapphire", m.substrate, "#dbe4ee"),
        ("SiC", m.substrate, "#4a5259"),
        ("GaN", m.semiconductor, "#7b6d8d"),
        ("SiO2", m.dielectric, "#8ecae6"),
        ("Al2O3", m.dielectric, "#a3cef1"),
        ("TiO2", m.dielectric, "#4f7396"),
        ("ITO", m.metal, "#bcd4d8"),
        ("GZO", m.metal, "#b8d0c8"),
        ("Al", m.metal, "#ced4da"),
        ("AlCu", m.metal, "#c6a892"),
        ("Ti", m.metal, "#6c757d"),
        ("Ni", m.metal, "#8a8478"),
        ("Photoresist", m.resist, "#f4a261"),
    ]
    return [Material(name=name, category=category, color=color) for name, category, color in entries]


register_library_file(
    LibraryFile(
        key="materials",
        filename="materiaux.yml",
        title="Matériaux",
        description="La liste proposée dans le sélecteur de matériau du constructeur de structure (nom, catégorie, couleur...) et les dégradés de couleur de l'InGaN et de l'AlGaN selon leur taux.",
        parse=_parse_materials_file,
        fallback=_builtin_materials_file,
        order=10,
    )
)
register_library_file(
    LibraryFile(
        key="recipes",
        filename="recettes.yml",
        title="Recettes",
        description="Recettes de dépôt/gravure supplémentaires (dont les gravures sélectives), fusionnées avec celles de StructureForge.",
        parse=_parse_recipes,
        fallback=lambda: ([], []),
        order=20,
    )
)
