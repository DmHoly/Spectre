"""API de consultation du dictionnaire de hooks (spectre/core/datahook) - lister les hooks
disponibles, voir la fiche de l'un d'eux (titre/description/paramètres attendus), et lancer sa
requête pour voir ce qu'elle renvoie. Page associée : /donnees (voir static/donnees.html).

Cette API parle à une vraie base PostgreSQL externe (voir spectre.core.datahook.connection) - les
erreurs de connexion/requête sont donc attendues (mauvais identifiants, base injoignable, requête
invalide) et renvoyées comme des 400/502 lisibles plutôt que de laisser remonter une trace psycopg2
brute.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.accounts import User
from ..core.datahook import connection, hooks
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donnees", tags=["donnees"])


def _hook_summary(key: str) -> dict[str, Any]:
    hook = hooks.load_hook(key)
    return {
        "key": hook.key,
        "title": hook.title,
        "description": hook.description,
        "parameters": hook.parameters,
        "postprocessing": hook.postprocessing,
    }


@router.get("/hooks")
def list_hooks(user: User = Depends(get_current_user)) -> dict:
    return {"hooks": [_hook_summary(key) for key in hooks.list_hooks()]}


@router.get("/hooks/{key}")
def get_hook(key: str, user: User = Depends(get_current_user)) -> dict:
    try:
        return _hook_summary(key)
    except hooks.HookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except hooks.HookDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class RunHookRequest(BaseModel):
    # Un paramètre de hook est toujours une liste de chaînes à ce jour (wafer_names...) - un champ
    # libre plutôt qu'un modèle par hook, puisque chaque hook déclare son propre jeu de paramètres.
    parameters: dict[str, list[str]] = {}


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
        hook = hooks.load_hook(key)
    except hooks.HookNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    missing = [p for p in hook.parameters if p not in body.parameters]
    if missing:
        raise HTTPException(status_code=422, detail=f"paramètre(s) manquant(s) : {missing}")

    try:
        df = hooks.run_hook(key, **body.parameters)
    except hooks.HookDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except connection.DatahookConfigError as exc:
        raise HTTPException(status_code=400, detail=f"configuration de connexion incomplète : {exc}") from exc
    except Exception as exc:  # psycopg2.Error et consorts - jamais une trace brute côté client
        logger.warning("hook %r : échec de la requête (%s)", key, exc)
        raise HTTPException(status_code=502, detail=f"la requête a échoué : {exc}") from exc

    columns = list(df.columns)
    rows = [[_json_safe(v) for v in row] for row in df.itertuples(index=False, name=None)]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
