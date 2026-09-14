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

``hook.yml`` porte aussi tout ce qu'il faut pour générer la page wiki (voir
:mod:`spectre.api.datahook`, ``static/donnees.html``) sans toucher au code Python : ``category``
(le regroupement affiché - "Post EPI", "Structure"...), ``status`` (``implemented`` - une vraie
requête existe - ou ``planned`` - fiche documentaire seule, pas encore de ``query.sql``),
``raw_columns``/``kpi_columns`` (niveau 1 : ce que la requête renvoie telle quelle ; niveau 2 : ce
que le post-traitement calcule ou recalcule - chaque colonne documentée porte ``name``,
``description``, un ``example`` et, pour une colonne KPI, sa ``source``), ``example_rows`` (un
petit échantillon écrit à la main pour illustrer la fiche sans dépendre de la base), et
``representative_column`` (la colonne mise en avant par défaut sur le graphique de la fiche).
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from . import cache, connection

logger = logging.getLogger(__name__)

HOOKS_DIR = Path(__file__).resolve().parent / "hooks"
POSTPROCESSING_PACKAGE = "spectre.core.datahook.postprocessing"


class HookNotFoundError(Exception):
    pass


class HookDefinitionError(Exception):
    """``hook.yml``/``query.sql`` manquant ou mal formé pour ce hook."""


@dataclass(frozen=True)
class ColumnDoc:
    """Une colonne documentée dans la page wiki d'un hook (voir spectre/api/datahook.py et
    static/donnees.html) : son nom, ce qu'elle représente, et - pour une colonne KPI, pas une
    colonne brute - d'où elle vient (quelle fonction de post-traitement la calcule).
    """

    name: str
    description: str
    example: Any = None
    source: str | None = None


@dataclass(frozen=True)
class DataHook:
    key: str
    title: str
    description: str
    parameters: list[str]
    postprocessing: list[str]
    sql: str
    # Le nom de la colonne (dans le résultat déjà post-traité) qui identifie le wafer d'une ligne -
    # ce qui permet de mettre ce hook en cache par wafer (voir run_hook_cached). None : ce hook ne
    # se prête pas au cache par wafer (ex. waferlist, qui ne prend pas de wafer_names du tout).
    cache_key_column: str | None
    # Wiki (voir README.md) : regroupement d'affichage ("Post EPI", "Structure"...), statut
    # ("implemented" - vraie requête exécutable - ou "planned" - fiche documentaire seule, pas
    # encore de query.sql), les deux niveaux de colonnes (brutes vs KPI calculés), un exemple de
    # ligne pour illustrer la fiche sans avoir à interroger la base, et la colonne mise en avant
    # par défaut sur le graphique représentatif de la page.
    category: str
    status: str
    raw_columns: list[ColumnDoc]
    kpi_columns: list[ColumnDoc]
    example_rows: list[dict[str, Any]]
    representative_column: str | None


def list_hooks() -> list[str]:
    """Toutes les clés de hook disponibles (un sous-dossier de ``hooks/`` = une clé), triées."""
    if not HOOKS_DIR.is_dir():
        return []
    return sorted(p.name for p in HOOKS_DIR.iterdir() if p.is_dir() and (p / "hook.yml").is_file())


def list_hooks_by_category() -> dict[str, list[DataHook]]:
    """Tous les hooks (implémentés ou non), groupés par ``category`` - l'ordre des catégories suit
    celui dans lequel leur premier hook est rencontré (ordre alphabétique des clés), pas un ordre
    éditorial fixe ; la page wiki peut réordonner à l'affichage si besoin.
    """
    grouped: dict[str, list[DataHook]] = {}
    for key in list_hooks():
        hook = load_hook(key)
        grouped.setdefault(hook.category, []).append(hook)
    return grouped


def _column_docs(entries: list[dict[str, Any]] | None) -> list[ColumnDoc]:
    out = []
    for entry in entries or []:
        out.append(
            ColumnDoc(
                name=entry["name"],
                description=entry.get("description", ""),
                example=entry.get("example"),
                source=entry.get("source"),
            )
        )
    return out


def load_hook(key: str) -> DataHook:
    hook_dir = HOOKS_DIR / key
    yml_path = hook_dir / "hook.yml"
    sql_path = hook_dir / "query.sql"
    if not yml_path.is_file():
        raise HookNotFoundError(f"hook inconnu : {key!r} ({yml_path} absent)")

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

    status = raw.get("status", "implemented")
    if status not in ("implemented", "planned"):
        raise HookDefinitionError(f"{yml_path} : status inconnu {status!r} (attendu implemented|planned)")

    # Un hook "planned" est une fiche documentaire pure : pas encore de requête réelle, donc pas de
    # query.sql à exiger - la page wiki l'affiche (catégorie, description, colonnes envisagées),
    # elle ne propose juste pas de bouton "lancer la requête" pour lui (voir status côté API).
    if status == "implemented" and not sql_path.is_file():
        raise HookDefinitionError(f"{sql_path} absent pour le hook implémenté {key!r}")
    sql = sql_path.read_text(encoding="utf-8") if sql_path.is_file() else ""

    return DataHook(
        key=key,
        title=title,
        description=description,
        parameters=list(raw.get("parameters") or []),
        postprocessing=list(raw.get("postprocessing") or []),
        sql=sql,
        cache_key_column=raw.get("cache_key_column"),
        category=raw.get("category", "Général"),
        status=status,
        raw_columns=_column_docs(raw.get("raw_columns")),
        kpi_columns=_column_docs(raw.get("kpi_columns")),
        example_rows=list(raw.get("example_rows") or []),
        representative_column=raw.get("representative_column"),
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
    if hook.status == "planned":
        raise HookDefinitionError(f"le hook {key!r} est une fiche documentaire (status: planned) - pas encore de requête à exécuter")
    missing = [p for p in hook.parameters if p not in params]
    if missing:
        raise HookDefinitionError(f"paramètre(s) manquant(s) pour le hook {key!r} : {missing}")

    df = connection.run_query(hook.sql, params)
    for step in hook.postprocessing:
        func = _resolve_postprocessing_function(step)
        df = func(df)
    return df


class CacheResult:
    """Le résultat de :func:`run_hook_cached` : le DataFrame combiné, plus le détail de quels
    wafers venaient du cache disque et lesquels viennent d'être requêtés (et donc mis en cache à
    l'instant) - utile à l'appelant pour l'afficher ("3 wafers en cache, 2 requêtés").
    """

    def __init__(self, df: pd.DataFrame, from_cache: list[str], fetched: list[str]):
        self.df = df
        self.from_cache = from_cache
        self.fetched = fetched


def run_hook_cached(key: str, wafer_names: list[str], refresh: bool = False) -> CacheResult:
    """Comme :func:`run_hook`, mais met le résultat en cache disque **par wafer**
    (:mod:`spectre.core.datahook.cache`) : un wafer déjà vu (par cette requête ou une précédente,
    même sur un lot différent) est relu instantanément depuis son fichier JSON plutôt que
    retaper la base ; seuls les wafers manquants (ou tous, si ``refresh=True``) déclenchent une
    vraie requête. Ne s'applique qu'aux hooks qui déclarent ``cache_key_column`` dans leur
    ``hook.yml`` - les autres (ex. ``waferlist``, qui ne prend pas ``wafer_names``) retombent sur
    :func:`run_hook` tel quel, sans mise en cache.
    """
    hook = load_hook(key)
    if not hook.cache_key_column:
        return CacheResult(run_hook(key, wafer_names=wafer_names), from_cache=[], fetched=list(wafer_names))

    from_cache_frames: list[pd.DataFrame] = []
    from_cache: list[str] = []
    missing: list[str] = []
    for wafer in wafer_names:
        cached_rows = None if refresh else cache.read_cached_rows(key, wafer)
        if cached_rows is None:
            missing.append(wafer)
        else:
            from_cache.append(wafer)
            from_cache_frames.append(pd.DataFrame(cached_rows))

    fetched_frames: list[pd.DataFrame] = []
    if missing:
        fresh_df = run_hook(key, wafer_names=missing)
        for wafer in missing:
            wafer_df = fresh_df[fresh_df[hook.cache_key_column] == wafer] if not fresh_df.empty else fresh_df
            cache.write_cache(key, wafer, wafer_df.to_dict(orient="records"))
        fetched_frames.append(fresh_df)

    frames = [f for f in (*from_cache_frames, *fetched_frames) if not f.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return CacheResult(combined, from_cache=from_cache, fetched=missing)
