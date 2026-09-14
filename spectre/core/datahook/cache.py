"""Cache disque du dictionnaire de hooks : le résultat d'un hook, déjà post-traité, pour UN wafer
donné, stocké en JSON plat sous ``data/datahook_cache/<hook>/<wafer>.json`` - pour le relire
instantanément la prochaine fois plutôt que de retaper la base à chaque affichage (utile pour le
système de graphique, qui veut souvent la même donnée pour plusieurs wafers à la fois).

Le cache est **par wafer**, pas par lot de wafers : une requête pour 5 wafers dont 3 déjà en cache
ne retape la base que pour les 2 manquants (voir :func:`spectre.core.datahook.hooks.run_hook_cached`),
et un même wafer déjà mis en cache par une requête précédente (même lancée pour un tout autre lot)
est instantanément réutilisé.

Pas de logique d'expiration ici - une mesure de caractérisation ne change pas rétroactivement une
fois faite ; c'est le bouton "forcer le rafraîchissement" côté appelant qui décide de retaper la
base (utile si une mesure a été refaite, ou pour repartir d'un post-traitement corrigé).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import data_dir

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_.-]")


def cache_dir(hook_key: str) -> Path:
    return data_dir() / "datahook_cache" / hook_key


def _wafer_filename(wafer_name: str) -> str:
    """Un nom de wafer vient de la base externe, pas de Spectre - jamais garanti "propre" comme
    nom de fichier (espace, slash...). Remplacé caractère par caractère plutôt que rejeté, pour
    qu'un nom inhabituel reste cachable (juste sous un nom de fichier légèrement différent).
    """
    return _UNSAFE_CHARS_RE.sub("_", wafer_name) + ".json"


def cache_path(hook_key: str, wafer_name: str) -> Path:
    return cache_dir(hook_key) / _wafer_filename(wafer_name)


def read_cached_rows(hook_key: str, wafer_name: str) -> list[dict[str, Any]] | None:
    """Les lignes déjà en cache pour ce wafer, ou ``None`` si jamais mises en cache (ou fichier
    illisible - traité comme une absence plutôt que de faire échouer tout l'appel).
    """
    path = cache_path(hook_key, wafer_name)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload.get("rows")


def write_cache(hook_key: str, wafer_name: str, rows: list[dict[str, Any]]) -> None:
    path = cache_path(hook_key, wafer_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hook": hook_key,
        "wafer_name": wafer_name,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def clear_cache(hook_key: str, wafer_name: str | None = None) -> None:
    """Retire un wafer du cache d'un hook (ou tout le cache de ce hook si ``wafer_name`` est
    omis) - utile si on sait qu'une mesure a été refaite plutôt que d'attendre le prochain
    rafraîchissement forcé.
    """
    if wafer_name is not None:
        cache_path(hook_key, wafer_name).unlink(missing_ok=True)
        return
    directory = cache_dir(hook_key)
    if directory.is_dir():
        for f in directory.glob("*.json"):
            f.unlink(missing_ok=True)
