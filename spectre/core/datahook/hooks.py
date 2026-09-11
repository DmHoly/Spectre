"""Un « hook » de données = un dossier sous ``hooks/<clé>/`` avec exactement deux fichiers :

- ``hook.yml`` : nom affiché, description ("ce qu'il y a derrière" - à quoi correspondent ces
  lignes, filtrées comment, sur quelle recette/statut), la liste des paramètres attendus (à ce
  jour : toujours ``wafer_names``, une liste d'identifiants physiques - voir
  ``Experiment.metadata["physical_tracking"]`` côté Spectre), et une liste optionnelle de
  fonctions de post-traitement à appliquer en chaîne sur le DataFrame brut renvoyé par la requête.
- ``query.sql`` : la requête elle-même, avec ses paramètres nommés ``%(wafer_names)s`` etc. (style
  psycopg2 - voir :func:`spectre.core.datahook.connection.run_query`).

Ça forme le "dictionnaire de données" : ``run_hook("pl", wafer_names=[...])`` renvoie un DataFrame
prêt à afficher ou à faire consommer par un graphique standard, sans que l'appelant ait besoin de
savoir où vit la vraie requête SQL ni comment les KPI qu'elle expose sont calculés.

Un post-traitement se référence par un chemin pointé ``module:fonction`` résolu dans
``spectre.core.datahook.postprocessing`` (voir ce module) - jamais du code arbitraire dans le YAML
lui-même, pour qu'un hook reste un fichier texte inspectable plutôt qu'un vecteur d'exécution.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from . import connection

logger = logging.getLogger(__name__)

HOOKS_DIR = Path(__file__).resolve().parent / "hooks"
POSTPROCESSING_PACKAGE = "spectre.core.datahook.postprocessing"


class HookNotFoundError(Exception):
    pass


class HookDefinitionError(Exception):
    """``hook.yml``/``query.sql`` manquant ou mal formé pour ce hook."""


@dataclass(frozen=True)
class DataHook:
    key: str
    title: str
    description: str
    parameters: list[str]
    postprocessing: list[str]
    sql: str


def list_hooks() -> list[str]:
    """Toutes les clés de hook disponibles (un sous-dossier de ``hooks/`` = une clé), triées."""
    if not HOOKS_DIR.is_dir():
        return []
    return sorted(p.name for p in HOOKS_DIR.iterdir() if p.is_dir() and (p / "hook.yml").is_file())


def load_hook(key: str) -> DataHook:
    hook_dir = HOOKS_DIR / key
    yml_path = hook_dir / "hook.yml"
    sql_path = hook_dir / "query.sql"
    if not yml_path.is_file():
        raise HookNotFoundError(f"hook inconnu : {key!r} ({yml_path} absent)")
    if not sql_path.is_file():
        raise HookDefinitionError(f"{sql_path} absent pour le hook {key!r}")

    try:
        raw = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise HookDefinitionError(f"{yml_path} illisible : {exc}") from exc
    if not isinstance(raw, dict):
        raise HookDefinitionError(f"{yml_path} doit être un mapping YAML")

    try:
        title = raw["title"]
        description = raw["description"]
    except KeyError as exc:
        raise HookDefinitionError(f"{yml_path} : champ manquant {exc}") from exc

    return DataHook(
        key=key,
        title=title,
        description=description,
        parameters=list(raw.get("parameters") or []),
        postprocessing=list(raw.get("postprocessing") or []),
        sql=sql_path.read_text(encoding="utf-8"),
    )


def _resolve_postprocessing_function(dotted_path: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """``"module:fonction"`` -> la fonction elle-même, résolue dans
    ``spectre.core.datahook.postprocessing`` (jamais un chemin arbitraire hors de ce paquet -
    un hook ne peut désigner que des fonctions qui y ont été délibérément ajoutées).
    """
    if ":" not in dotted_path:
        raise HookDefinitionError(f"post-traitement mal formé (attendu 'module:fonction') : {dotted_path!r}")
    module_name, func_name = dotted_path.split(":", 1)
    try:
        module = importlib.import_module(f"{POSTPROCESSING_PACKAGE}.{module_name}")
    except ImportError as exc:
        raise HookDefinitionError(f"module de post-traitement introuvable : {module_name!r} ({exc})") from exc
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        raise HookDefinitionError(f"fonction de post-traitement introuvable : {dotted_path!r}")
    return func


def run_hook(key: str, **params: Any) -> pd.DataFrame:
    """Charge le hook ``key``, exécute sa requête avec ``params`` (typiquement
    ``wafer_names=[...]``), puis applique en chaîne chacune de ses fonctions de post-traitement -
    chacune reçoit le DataFrame renvoyé par la précédente (ou par la requête pour la première) et
    doit renvoyer un DataFrame à son tour.
    """
    hook = load_hook(key)
    missing = [p for p in hook.parameters if p not in params]
    if missing:
        raise HookDefinitionError(f"paramètre(s) manquant(s) pour le hook {key!r} : {missing}")

    df = connection.run_query(hook.sql, params)
    for step in hook.postprocessing:
        func = _resolve_postprocessing_function(step)
        df = func(df)
    return df
