"""Bibliothèque racine éditable (« registry ») : les matériaux, présets d'étape et briques
technologiques *par défaut* de cette instance Spectre, définis dans des fichiers YAML à la racine
du dépôt (``library/``) plutôt qu'en dur dans le code.

Le but : qu'une équipe fasse évoluer son vocabulaire (une liste de matériaux resserrée sur les
nitrures, ses présets de gravure maison, ses briques récurrentes...) en éditant un fichier texte,
sans toucher au code ni redémarrer le serveur.

- **Emplacement** : ``$SPECTRE_LIBRARY_DIR`` si la variable est définie, sinon ``<racine du
  dépôt>/library``.
- **Fichiers** : ``materiaux.yml``, ``presets.yml``, ``briques.yml`` — chacun optionnel. Absent ou
  illisible → on retombe sur le jeu intégré (voir ``_builtin_*``), en journalisant un avertissement.
- **Rechargement à chaud** : le contenu est mis en cache par fichier et réévalué dès que le fichier
  change (mtime), donc une modification est visible au prochain rafraîchissement de page.

Ces trois collections alimentent le *scope « preset »* des trois-buckets (intégré / partagé /
projet) déjà en place — voir :func:`spectre.api.keyed_resource.list_three_buckets`. Rien ici n'est
écrit : les stores JSON par projet/partagés restent le seul endroit modifiable depuis l'app.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from structureforge.core.materials import Material, MaterialCategory
from structureforge.core.recipes import DepositionRecipe, EtchRecipe

from .step_presets import DepositionPreset, EtchPreset, StepPreset, _builtin_step_presets
from .tech_bricks import TechBrick, _builtin_tech_bricks

logger = logging.getLogger(__name__)

# Par (fichier, clé) : (mtime au dernier chargement, liste de dicts bruts) - voir _raw_entries.
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def library_dir() -> Path:
    """Le dossier de la bibliothèque racine - ``$SPECTRE_LIBRARY_DIR`` ou ``<dépôt>/library``.
    Ancré sur l'emplacement de ce fichier (``spectre/core/registry.py``) et non sur le répertoire
    courant, pour que les tests et un lancement depuis n'importe où trouvent le même dossier.
    """
    override = os.environ.get("SPECTRE_LIBRARY_DIR")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2] / "library"


def _raw_entries(filename: str, key: str) -> list[dict[str, Any]] | None:
    """La liste sous ``key`` dans ``library/<filename>``, ou ``None`` si le fichier est absent ou
    illisible (l'appelant retombe alors sur son jeu intégré). Mise en cache tant que le mtime du
    fichier ne bouge pas.
    """
    path = library_dir() / filename
    cache_key = f"{filename}:{key}"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = list(data.get(key) or [])
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Bibliothèque racine : %s illisible (%s) - jeu intégré utilisé.", path, exc)
        return None
    _CACHE[cache_key] = (mtime, entries)
    return entries


def registry_materials() -> list[Material]:
    """Les matériaux proposés dans le sélecteur du constructeur de structure - la liste éditable
    ``library/materiaux.yml`` si elle existe, sinon :func:`_builtin_materials`. L'ordre du fichier
    est conservé (il pilote l'ordre du menu déroulant). La simulation, elle, résout toujours
    n'importe quel nom (voir :func:`spectre.core.structures.materials_library`).
    """
    entries = _raw_entries("materiaux.yml", "materials")
    if entries is None:
        return _builtin_materials()
    try:
        return [_material_from_entry(e) for e in entries]
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Bibliothèque racine : materiaux.yml invalide (%s) - jeu intégré utilisé.", exc)
        return _builtin_materials()


def registry_step_presets() -> dict[str, StepPreset]:
    """Présets d'étape par défaut - ``library/presets.yml`` si présent, sinon
    :func:`spectre.core.step_presets._builtin_step_presets`.
    """
    entries = _raw_entries("presets.yml", "presets")
    if entries is None:
        return _builtin_step_presets()
    try:
        presets = [_step_preset_from_entry(e) for e in entries]
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Bibliothèque racine : presets.yml invalide (%s) - jeu intégré utilisé.", exc)
        return _builtin_step_presets()
    return {p.name: p for p in presets}


def registry_tech_bricks() -> dict[str, TechBrick]:
    """Briques technologiques par défaut - ``library/briques.yml`` si présent, sinon
    :func:`spectre.core.tech_bricks._builtin_tech_bricks` (vide à ce jour).
    """
    entries = _raw_entries("briques.yml", "bricks")
    if entries is None:
        return _builtin_tech_bricks()
    try:
        bricks = [_tech_brick_from_entry(e) for e in entries]
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Bibliothèque racine : briques.yml invalide (%s) - jeu intégré utilisé.", exc)
        return _builtin_tech_bricks()
    return {b.name: b for b in bricks}


def registry_recipes() -> tuple[list[DepositionRecipe], list[EtchRecipe]]:
    """Recettes de dépôt / gravure *supplémentaires* définies dans ``library/recettes.yml`` (clés
    ``deposition:`` et ``etch:``), fusionnées par-dessus celles de StructureForge - c'est ici, et
    pas dans un préset, que vit une gravure sélective (``selectivity_by_material`` /
    ``selectivity_by_category`` / ``default_factor``). Fichier absent ou invalide → ``([], [])`` :
    on garde alors uniquement les recettes intégrées de StructureForge.
    """
    dep_entries = _raw_entries("recettes.yml", "deposition")
    etch_entries = _raw_entries("recettes.yml", "etch")
    if dep_entries is None and etch_entries is None:
        return [], []
    try:
        deposition = [DepositionRecipe(**_drop_none(e)) for e in (dep_entries or [])]
        etches = [EtchRecipe(**_drop_none(e)) for e in (etch_entries or [])]
    except (TypeError, ValueError) as exc:
        logger.warning("Bibliothèque racine : recettes.yml invalide (%s) - recettes intégrées seules.", exc)
        return [], []
    return deposition, etches


def _drop_none(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if v is not None}


def _material_from_entry(entry: dict[str, Any]) -> Material:
    category = entry.get("category", "other")
    if category not in {c.value for c in MaterialCategory}:
        raise ValueError(f"catégorie de matériau inconnue : {category!r}")
    fields = {"name": entry["name"], "category": category}
    for optional in ("color", "density_g_cm3", "refractive_index", "notes"):
        if entry.get(optional) is not None:
            fields[optional] = entry[optional]
    return Material(**fields)


def _step_preset_from_entry(entry: dict[str, Any]) -> StepPreset:
    kind = entry["kind"]
    if kind == "deposition":
        payload: DepositionPreset | EtchPreset = DepositionPreset(recipe=entry["recipe"])
    elif kind == "etch":
        payload = EtchPreset(recipe=entry["recipe"])
    else:
        raise ValueError(f"type de préset inconnu : {kind!r} (attendu deposition ou etch)")
    return StepPreset(name=entry["name"], payload=payload, notes=entry.get("notes"), created_at="preset")


def _tech_brick_from_entry(entry: dict[str, Any]) -> TechBrick:
    return TechBrick.model_validate(
        {"name": entry["name"], "notes": entry.get("notes"), "steps": entry.get("steps") or [], "created_at": "preset"}
    )


def _builtin_materials() -> list[Material]:
    """Repli quand ``library/materiaux.yml`` est absent : une liste resserrée orientée nitrures /
    semi-conducteurs (mêmes couleurs que la bibliothèque StructureForge d'origine pour que le rendu
    ne change pas), plus deux oxydes conducteurs / alliages absents de StructureForge (GZO, AlCu).
    AlGaN / InGaN ne sont pas listés : ce sont toujours des compositions à taux précis, composées à
    la volée depuis le champ matériau. Le fichier YAML livré reprend exactement cette liste.
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
