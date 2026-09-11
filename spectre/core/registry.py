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

# Par fichier : (mtime au dernier chargement, dict brut) - voir _raw_mapping (fichiers qui sont un
# seul objet de config, pas une collection de {key: [...]}).
_MAPPING_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


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


def _raw_mapping(filename: str) -> dict[str, Any] | None:
    """Le contenu de ``library/<filename>`` comme un dict brut (fichier qui *est* un seul objet de
    config, pas une collection de ``{key: [...]}`` comme ``_raw_entries``). ``None`` si le fichier
    est absent ou illisible - l'appelant retombe alors sur son jeu intégré. Mise en cache tant que
    le mtime du fichier ne bouge pas.
    """
    path = library_dir() / filename
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _MAPPING_CACHE.get(filename)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise TypeError(f"attendu un mapping, reçu {type(data).__name__}")
    except (yaml.YAMLError, OSError, TypeError) as exc:
        logger.warning("Bibliothèque racine : %s illisible (%s) - jeu intégré utilisé.", path, exc)
        return None
    _MAPPING_CACHE[filename] = (mtime, data)
    return data


def registry_intention_form() -> dict[str, Any]:
    """La copie (libellés/placeholders/aides) de la section « Objectifs et intention » du
    constructeur de structure - ``library/intention.yml`` si présent, sinon
    :func:`_builtin_intention_form`. Fusionnée par-dessus le jeu intégré clé par clé, pour qu'un
    fichier partiel (qui n'override que quelques libellés) reste valide.
    """
    data = _raw_mapping("intention.yml")
    builtin = _builtin_intention_form()
    if data is None:
        return builtin
    merged = {**builtin, **data}
    return merged


def _builtin_intention_form() -> dict[str, Any]:
    """Repli quand ``library/intention.yml`` est absent : la copie française telle qu'elle était
    codée en dur jusqu'ici dans structure-builder.html.
    """
    return {
        "section_title": "Objectifs et intention",
        "section_subtitle": (
            "Pourquoi cette expérience, ce qu'on cherche à savoir, et comment on saura si c'est atteint."
        ),
        "title_label": "Titre de l'expérience",
        "title_placeholder": "ex : Contact ohmique PGaN, dopage cible",
        "intent_label": "Intention (pourquoi fait-on cette expérience ?)",
        "intent_placeholder": "Que cherche-t-on à vérifier, et pourquoi maintenant ?",
        "hypothesis_label": "Hypothèse (optionnelle)",
        "hypothesis_placeholder": "Ce qu'on pense observer",
        "entity_field_label": "Entité physique (obligatoire)",
        "entity_id_placeholder": "ex : W12-A3",
        "entity_location_label": "Emplacement (optionnel)",
        "entity_location_placeholder": "ex : congélateur B, tiroir 2",
        "entity_field_hint": (
            "Chaque expérience doit être reliée à un échantillon réel - c'est cet identifiant qui "
            "permet de la retrouver."
        ),
        "objectives_title": "Objectifs",
        "objective_name_label": "Objectif",
        "objective_name_placeholder": "ex : isolation électrique",
        "objective_rationale_label": "Pourquoi cet objectif",
        "objective_rationale_placeholder": "ex : condition pour passer en production",
        "objective_metric_label": "Mesure",
        "objective_metric_placeholder": "ex : resistivity_ohm_cm",
        "objective_direction_label": "Sens",
        "objective_target_label": "Valeur cible (optionnelle)",
        "objective_verification_label": "Comment on compte le vérifier",
        "objective_verification_placeholder": "ex : mesure au profilomètre après dépôt",
        "objective_submit_label": "Ajouter l'objectif",
        "objective_directions": [
            {"value": "observe", "label": "Observer", "color": "#2f6fb0"},
            {"value": "maximize", "label": "Maximiser", "color": "#2f8f5b"},
            {"value": "minimize", "label": "Minimiser", "color": "#b5842a"},
            {"value": "target", "label": "Cible précise", "color": "#7b4fa3"},
        ],
    }


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


def validate_library_yaml(filename: str, text: str) -> None:
    """Valide le contenu ``text`` comme un ``library/<filename>`` acceptable, ou lève
    ``ValueError`` avec un message expliquant quoi corriger. N'écrit rien sur disque - c'est
    l'appelant (l'endpoint d'édition) qui s'en charge une fois cette fonction passée sans lever.
    """
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML invalide : {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"le fichier doit être un mapping YAML (clé: valeur), reçu {type(data).__name__}")

    if filename == "intention.yml":
        return  # mapping plat, fusionné clé par clé - toute clé/valeur est acceptable ici

    if filename == "recettes.yml":
        for key, factory in (("deposition", DepositionRecipe), ("etch", EtchRecipe)):
            entries = data.get(key) or []
            if not isinstance(entries, list):
                raise ValueError(f"'{key}' doit être une liste")
            for i, entry in enumerate(entries):
                try:
                    factory(**_drop_none(entry))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{key}[{i}] invalide : {exc}") from exc
        return

    key, factory = _VALIDATORS.get(filename, (None, None))
    if key is None:
        raise ValueError(f"fichier de bibliothèque inconnu : {filename!r}")
    entries = data.get(key)
    if not isinstance(entries, list):
        raise ValueError(f"le fichier doit contenir une clé '{key}' avec une liste")
    for i, entry in enumerate(entries):
        try:
            factory(entry)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{key}[{i}] invalide : {exc}") from exc


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


# Un fichier -> (la clé "collection" attendue, la fonction qui valide chaque entrée - jetée si
# invalide). Utilisé par validate_library_yaml() ci-dessus - la seule porte d'entrée pour un "save"
# côté bibliothèque éditable en ligne (voir spectre.api.library) : contrairement aux registry_*()
# plus haut, qui retombent silencieusement sur le jeu intégré si le fichier est invalide
# (comportement voulu pour ne jamais casser l'appli sur un fichier mal édité à la main), on doit ici
# pouvoir dire *pourquoi* c'est invalide avant d'écrire quoi que ce soit sur disque.
_VALIDATORS: dict[str, tuple[str, Any]] = {
    "materiaux.yml": ("materials", _material_from_entry),
    "presets.yml": ("presets", _step_preset_from_entry),
    "briques.yml": ("bricks", _tech_brick_from_entry),
}


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
