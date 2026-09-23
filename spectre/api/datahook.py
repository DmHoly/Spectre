"""API de consultation du dictionnaire de données PRISM (paquet ``prism-aledia-datahook``, voir
https://gitlab-it.aledia.com/sda/tools/soft/prism) - lister les hooks disponibles, voir la fiche de
l'un d'eux (titre/description/paramètres attendus), et lancer sa requête pour voir ce qu'elle
renvoie. Page associée : /donnees (voir static/donnees.html).

Spectre ne porte plus aucune requête ni formule KPI : tout vit dans PRISM, partagé avec les autres
projets. Ce module n'est que l'adaptateur HTTP. PRISM parle à de vraies bases externes (profils de
``~/.prism/connections.yml``) - les erreurs de configuration/connexion/requête sont donc attendues
(identifiants absents, base injoignable, requête invalide) et renvoyées comme des 400/502 lisibles
plutôt que de laisser remonter une trace brute.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import prism

from ..core.accounts import User
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donnees", tags=["donnees"])


def _column_doc_json(col: prism.ColumnDoc) -> dict[str, Any]:
    return {
        "name": col.name,
        "description": col.description,
        "example": col.example,
        "source": col.source,
        "formula": col.formula,
        "unit": col.unit,
    }


def _hook_summary(key: str) -> dict[str, Any]:
    hook = prism.load_hook(key)
    return {
        "key": hook.key,
        "title": hook.title,
        "description": hook.description,
        "parameters": hook.parameters,
        "postprocessing": hook.postprocessing,
        "cacheable": bool(hook.cache_key_column) and "wafer_names" in hook.parameters,
        "category": hook.category,
        "status": hook.status,
        "raw_columns": [_column_doc_json(c) for c in hook.raw_columns],
        "kpi_columns": [_column_doc_json(c) for c in hook.kpi_columns],
        "example_rows": hook.example_rows,
        "representative_column": hook.representative_column,
        "charts": [{"key": c.key, "title": c.title, "description": c.description} for c in hook.charts],
    }


@router.get("/hooks")
def list_hooks(user: User = Depends(get_current_user)) -> dict:
    return {"hooks": [_hook_summary(key) for key in prism.list_hooks()]}


@router.get("/categories")
def list_categories(user: User = Depends(get_current_user)) -> dict:
    """Le regroupement de la page wiki (voir static/donnees.html) : chaque catégorie ("Post EPI",
    "Structure"...) avec ses hooks, implémentés et "planned" (fiche documentaire seule) mêlés -
    c'est ``status`` sur chaque hook qui dit à la page s'il propose un bouton "lancer la requête".
    """
    grouped = prism.list_hooks_by_category()
    return {"categories": [{"name": name, "hooks": [_hook_summary(h.key) for h in hs]} for name, hs in grouped.items()]}


@router.get("/hooks/{key}")
def get_hook(key: str, user: User = Depends(get_current_user)) -> dict:
    try:
        return _hook_summary(key)
    except prism.HookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except prism.HookDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class RunHookRequest(BaseModel):
    # Un paramètre de hook est toujours une liste de chaînes à ce jour (wafer_names...) - un champ
    # libre plutôt qu'un modèle par hook, puisque chaque hook déclare son propre jeu de paramètres.
    parameters: dict[str, list[str]] = {}
    # Ignore le cache disque et retape la base pour tous les wafers demandés - utile si une mesure
    # a été refaite depuis la dernière consultation. Sans effet sur un hook non cacheable
    # (cache_key_column absent, ex. waferlist).
    refresh: bool = False


def _json_safe(value: Any) -> Any:
    """Une valeur de cellule DataFrame telle quelle n'est pas forcément JSON-sérialisable
    (NaN, NaT, Timestamp, date, ou un vecteur numpy pour une colonne "spectre") - convertie ici en
    quelque chose que ``json.dumps`` accepte tel quel, sans changer sa forme (une liste reste une
    liste), plutôt que de la perdre en la forçant en chaîne.
    """
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar (int64, float64...)
        return _json_safe(value.item())
    return value


@router.post("/hooks/{key}/executer")
def run_hook(key: str, body: RunHookRequest, user: User = Depends(get_current_user)) -> dict:
    try:
        hook = prism.load_hook(key)
    except prism.HookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if hook.status == "planned":
        raise HTTPException(status_code=422, detail="ce hook est une fiche documentaire (pas encore implémenté) - pas de requête à lancer")

    missing = [p for p in hook.parameters if p not in body.parameters]
    if missing:
        raise HTTPException(status_code=422, detail=f"paramètre(s) manquant(s) : {missing}")

    cache_summary: dict[str, Any] = {}
    try:
        if hook.cache_key_column and "wafer_names" in hook.parameters:
            result = prism.run_hook_cached(key, wafer_names=body.parameters.get("wafer_names", []), refresh=body.refresh)
            df = result.df
            cache_summary = {"from_cache": result.from_cache, "fetched": result.fetched}
        else:
            df = prism.run_hook(key, **body.parameters)
    except prism.HookDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except prism.ConfigError as exc:
        raise HTTPException(status_code=400, detail=f"configuration de connexion incomplète : {exc}") from exc
    except Exception as exc:  # ConnectionFailed, QueryFailed, post-traitement - jamais une trace brute côté client
        logger.warning("hook %r : échec de la requête (%s)", key, exc)
        raise HTTPException(status_code=502, detail=f"la requête a échoué : {exc}") from exc

    columns = list(df.columns)
    rows = [[_json_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return {"columns": columns, "rows": rows, "row_count": len(rows), **cache_summary}


@router.get("/hooks/{key}/graphiques/{chart_key}")
def get_hook_chart(key: str, chart_key: str, user: User = Depends(get_current_user)) -> Response:
    """Rend en PNG un graphique déclaré par ce hook (voir hook.yml -> charts, et
    prism.charts). Toujours dessiné sur l'exemple figé du hook.yml (``charts[].
    example``), jamais sur une vraie requête : la page wiki documente les données, elle ne relance
    aucun calcul à l'affichage."""
    try:
        png = prism.render_chart(key, chart_key)
    except prism.HookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except prism.HookDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("hook %r : échec du graphique %r (%s)", key, chart_key, exc)
        raise HTTPException(status_code=502, detail=f"le graphique a échoué : {exc}") from exc

    return Response(content=png, media_type="image/png")
