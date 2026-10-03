"""Bibliothèque racine éditable de l'instance : le vocabulaire *par défaut* (matériaux, recettes,
présets d'étape, briques, textes d'interface) en fichiers YAML plutôt qu'en dur dans le code, pour
qu'une équipe le fasse évoluer sans toucher au code ni redémarrer le serveur.

- **Emplacement** : ``$SPECTRE_LIBRARY_DIR`` si la variable est définie, sinon ``<données>/library``.
  Un dossier absent est créé une fois, à la première lecture, depuis les fichiers livrés
  (``spectre/plugins/library/defaults/``) ; il appartient ensuite à l'instance : une édition ne
  touche pas au dépôt, et une mise à jour du code n'écrase pas les éditions.
- **Registre** : cette bibliothèque ne connaît aucun type métier. Chaque plugin propriétaire déclare
  ses fichiers (:func:`register_library_file`) avec la fonction qui en interprète le contenu - et
  lève ``ValueError`` s'il est invalide - et son repli intégré.
- **Lecture** (:func:`load`) : le contenu interprété, en cache tant que le fichier ne change pas.
  Un fichier absent ou invalide donne le repli, avec un avertissement dans le journal : une édition
  à la main ratée ne casse jamais l'application.
- **Écriture** (:func:`save`) : le texte est interprété par la même fonction *avant* d'être écrit ;
  invalide, il est refusé avec le message de l'erreur.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from ...kernel.db import data_dir
from ...kernel.errors import InvalidInput, NotFound
from ...kernel.locks import keyed_lock

logger = logging.getLogger(__name__)

DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"


@dataclass(frozen=True)
class LibraryFile:
    """Un fichier de la bibliothèque, déclaré par le plugin qui en possède le contenu."""

    key: str  # son identifiant dans l'API : /api/library/files/{file_key}
    filename: str  # dans le dossier de la bibliothèque
    title: str
    description: str  # une ligne, affichée sur sa carte
    parse: Callable[[dict[str, Any]], Any]  # le mapping YAML lu -> le contenu interprété ; ValueError si invalide
    fallback: Callable[[], Any]  # le contenu quand le fichier est absent ou invalide
    order: int = 100  # ordre d'affichage


_FILES: dict[str, LibraryFile] = {}

# Par chemin : ((mtime_ns, taille) au dernier chargement, contenu interprété).
_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}


def register_library_file(file: LibraryFile) -> None:
    _FILES[file.key] = file


def library_files() -> list[LibraryFile]:
    return sorted(_FILES.values(), key=lambda file: (file.order, file.key))


def get_library_file(key: str) -> LibraryFile:
    file = _FILES.get(key)
    if file is None:
        raise NotFound(f"Fichier de bibliothèque inconnu : {key!r}.")
    return file


def library_dir() -> Path:
    """Le dossier de la bibliothèque, créé depuis les fichiers livrés s'il n'existe pas encore."""
    override = os.environ.get("SPECTRE_LIBRARY_DIR")
    path = Path(override).resolve() if override else data_dir() / "library"
    if not path.exists():
        with keyed_lock("library", "init"):
            if not path.exists():
                shutil.copytree(DEFAULTS_DIR, path, ignore=shutil.ignore_patterns("*.md"))
    return path


def read_text(file: LibraryFile) -> str | None:
    """Le texte du fichier, ou ``None`` s'il n'existe pas (ou plus)."""
    try:
        return (library_dir() / file.filename).read_text(encoding="utf-8")
    except OSError:
        return None


def parse_text(file: LibraryFile, text: str) -> Any:
    """Le contenu interprété de ``text`` ; ``ValueError`` avec un message qui dit quoi corriger."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML invalide : {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"le fichier doit être un mapping YAML (clé: valeur), reçu {type(data).__name__}")
    return file.parse(data)


def load(key: str) -> Any:
    """Le contenu interprété du fichier ``key`` - son repli s'il est absent ou invalide."""
    file = get_library_file(key)
    path = library_dir() / file.filename
    try:
        stat = path.stat()
    except OSError:
        return file.fallback()
    signature = (stat.st_mtime_ns, stat.st_size)
    cached = _CACHE.get(str(path))
    if cached is not None and cached[0] == signature:
        return cached[1]
    try:
        content = parse_text(file, path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Bibliothèque racine : %s invalide (%s) - jeu intégré utilisé.", path, exc)
        content = file.fallback()
    _CACHE[str(path)] = (signature, content)
    return content


def save(key: str, text: str) -> None:
    """Valide ``text`` puis remplace le fichier ``key`` (écriture atomique) ; ``InvalidInput`` si
    le contenu est invalide - rien n'est alors écrit."""
    file = get_library_file(key)
    try:
        parse_text(file, text)
    except ValueError as exc:
        raise InvalidInput(str(exc), code="invalid_library_file") from exc
    path = library_dir() / file.filename
    with keyed_lock("library", file.filename):
        fd, tmp = tempfile.mkstemp(prefix=f".{file.filename}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def parse_entries(data: dict[str, Any], key: str, parse_entry: Callable[[dict[str, Any]], Any], *, required: bool = True) -> list[Any]:
    """Les éléments de la liste ``data[key]``, chacun interprété par ``parse_entry`` - l'outil des
    fichiers qui sont une collection (``materials: [...]``). ``ValueError`` qui nomme l'élément fautif."""
    entries = data.get(key)
    if entries is None and not required:
        return []
    if not isinstance(entries, list):
        raise ValueError(f"le fichier doit contenir une clé '{key}' avec une liste")
    parsed = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{key}[{i}] invalide : attendu un mapping (clé: valeur)")
        try:
            parsed.append(parse_entry(entry))
        except KeyError as exc:
            raise ValueError(f"{key}[{i}] invalide : champ obligatoire manquant {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key}[{i}] invalide : {exc}") from exc
    return parsed


# -- textes d'interface ----------------------------------------------------------------------------


def _intention_texts(data: dict[str, Any]) -> dict[str, Any]:
    """Un fichier partiel (qui ne redéfinit que quelques libellés) reste valide : il est fusionné
    par-dessus le jeu intégré, clé par clé."""
    return {**_builtin_intention_texts(), **data}


def _builtin_intention_texts() -> dict[str, Any]:
    """Repli quand ``intention.yml`` est absent : la copie française d'origine du constructeur."""
    return {
        "section_title": "Intention & objectifs",
        "section_subtitle": (
            "Le contexte, ce que je veux démontrer, et comment je compte le faire - c'est ce qu'on lira "
            "en tête de la fiche."
        ),
        "title_label": "Titre de l'expérience",
        "title_placeholder": "ex : Contact ohmique PGaN, dopage cible",
        "context_label": "Contexte (description sommaire)",
        "context_placeholder": (
            "D'où part cette expérience, pourquoi maintenant - ex : suite du run W40, la directivité "
            "chutait sur les plaques pixélisées"
        ),
        "intent_label": "Ce que je veux démontrer",
        "intent_placeholder": "ex : la pixélisation au niveau du contact P ne change pas la directivité",
        "hypothesis_label": "Hypothèse (optionnelle)",
        "hypothesis_placeholder": "Ce qu'on pense observer",
        "entity_field_label": "Plaque suivie - lasermark (obligatoire)",
        "entity_id_placeholder": "ex : W12-A3",
        "entity_location_label": "Emplacement (optionnel)",
        "entity_location_placeholder": "ex : congélateur B, tiroir 2",
        "entity_field_hint": (
            "Chaque expérience doit être reliée à un échantillon réel - c'est cet identifiant qui "
            "permet de la retrouver."
        ),
        "objectives_title": "Comment je compte le démontrer (objectifs)",
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


# Les textes de la section « Objectifs et intention » du constructeur, servis par
# GET /api/ui-texts/intention.
register_library_file(
    LibraryFile(
        key="intention",
        filename="intention.yml",
        title="Formulaire d'intention",
        description="Les libellés, placeholders et couleurs de la section « Objectifs et intention » du constructeur de structure.",
        parse=_intention_texts,
        fallback=_builtin_intention_texts,
        order=50,
    )
)
