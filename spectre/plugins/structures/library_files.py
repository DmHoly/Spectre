"""Les fichiers de la bibliothèque racine que possède ce plugin (``materiaux.yml``,
``recettes.yml``), déclarés au registre de ``library`` avec leur interprétation et leur repli."""

from __future__ import annotations

from typing import Any

from structureforge.core.materials import Material, MaterialCategory
from structureforge.core.recipes import DepositionRecipe, EtchRecipe

from ..library.service import LibraryFile, load, parse_entries, register_library_file


def materials() -> list[Material]:
    """Les matériaux proposés dans le sélecteur du constructeur, dans l'ordre du fichier (il pilote
    l'ordre du menu). La simulation, elle, résout toujours n'importe quel nom connu de StructureForge."""
    return load("materials")


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


def _drop_none(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if v is not None}


def _parse_recipes(data: dict[str, Any]) -> tuple[list[DepositionRecipe], list[EtchRecipe]]:
    deposition = parse_entries(data, "deposition", lambda e: DepositionRecipe(**_drop_none(e)), required=False)
    etch = parse_entries(data, "etch", lambda e: EtchRecipe(**_drop_none(e)), required=False)
    return deposition, etch


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
        description="La liste proposée dans le sélecteur de matériau du constructeur de structure (nom, catégorie, couleur...).",
        parse=lambda data: parse_entries(data, "materials", _material_from_entry),
        fallback=_builtin_materials,
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
