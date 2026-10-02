"""Les données de caractérisation : ce que PRISM (paquet ``prism-aledia-datahook``) sait servir - la
liste des requêtes implémentées - et l'exécution de l'une d'elles pour un lot de plaques.

Données de démonstration : avec ``SPECTRE_DEMO_DATA=1`` (instance de démo sans accès aux bases),
les requêtes sont servies par :mod:`spectre.plugins.characterization.demo` au lieu de PRISM, et le
disent (``source: "demo"``) - jamais par défaut, jamais en repli silencieux d'une base injoignable.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    """Une requête qui n'a pas pu aboutir - ``status_code`` dit pourquoi (400 configuration, 404
    type inconnu, 422 demande invalide, 502 base injoignable / requête en échec)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def demo_enabled() -> bool:
    return os.environ.get("SPECTRE_DEMO_DATA") == "1"


def json_safe(value: Any) -> Any:
    """Une cellule de DataFrame en quelque chose que ``json.dumps`` accepte, sans changer sa forme
    (NaN -> None, horodatage -> ISO, scalaire/vecteur numpy -> Python)."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        return json_safe(value.tolist())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_safe(value.item())
    return value


def available_sources() -> list[dict[str, Any]]:
    """Les types de données qu'un cahier peut charger : les requêtes PRISM implémentées."""
    try:
        import prism
    except ImportError:  # PRISM absent : rien à proposer
        return []
    sources = []
    for key in prism.list_hooks():
        try:
            hook = prism.load_hook(key)
        except Exception:  # une fiche mal formée ne doit pas casser la liste
            continue
        if hook.status != "implemented":
            continue
        sources.append(
            {
                "key": hook.key,
                "title": hook.title,
                "category": hook.category,
                "description": hook.description,
                "by_wafer": "wafer_names" in hook.parameters,
                "representative_column": hook.representative_column,
            }
        )
    return sources


def _run_prism(hook_key: str, wafers: list[str], refresh: bool) -> tuple[list[str], list[list[Any]]]:
    import prism

    try:
        hook = prism.load_hook(hook_key)
    except prism.HookNotFoundError as exc:
        raise DataSourceError(404, f"type de données inconnu : {hook_key}") from exc
    if hook.status != "implemented":
        raise DataSourceError(422, "ce type de données n'est pas encore disponible (fiche documentaire)")
    by_wafer = "wafer_names" in hook.parameters
    if by_wafer and not wafers:
        raise DataSourceError(422, "indiquez au moins une plaque (lasermark)")
    try:
        if hook.cache_key_column and by_wafer:
            df = prism.run_hook_cached(hook_key, wafer_names=wafers, refresh=refresh).df
        elif by_wafer:
            df = prism.run_hook(hook_key, wafer_names=wafers)
        else:
            df = prism.run_hook(hook_key)
    except prism.HookDefinitionError as exc:
        raise DataSourceError(400, str(exc)) from exc
    except prism.ConfigError as exc:
        raise DataSourceError(400, f"configuration de connexion PRISM incomplète : {exc}") from exc
    except Exception as exc:  # base injoignable, requête ou post-traitement en échec
        logger.warning("cahier : requête %r en échec (%s)", hook_key, exc)
        raise DataSourceError(502, f"la requête PRISM a échoué : {exc}") from exc
    columns = [str(c) for c in df.columns]
    rows = [[json_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return columns, rows


def query(hook_key: str, wafers: list[str], *, refresh: bool = False) -> tuple[str, list[str], list[list[Any]]]:
    """``(source, columns, rows)`` : la requête ``hook_key`` pour ces plaques - PRISM, ou la démo si
    elle est activée."""
    if demo_enabled():
        from .demo import generate

        columns, rows = generate(hook_key, wafers)
        return "demo", columns, rows
    columns, rows = _run_prism(hook_key, wafers, refresh)
    return "prism", columns, rows


def title_of(hook_key: str) -> str:
    return next((s["title"] for s in available_sources() if s["key"] == hook_key), hook_key)
