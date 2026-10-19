"""Les images MEB du G4 d'une plaque, telles que la page de la plaque les montre : rangées par acquisition (un
dossier de wafer = une FDL, un procédé, une étape), lues à leur place sur le partage, jamais copiées.

- **où chercher** : les FDL que Spectre connaît à la plaque (sa vie en ligne, ses études) et celles qu'on tape
  sur la page ; PRISM y ajoute son index des dossiers (le partage n'en a pas) ;
- **la liste** se garde :data:`LISTING_TTL` secondes en mémoire par plaque (relue sur demande) ; c'est elle qui
  dit quelles images on peut servir - une image se demande par son chemin relatif à la racine, et seul un chemin
  de la liste de cette plaque est lu ;
- **l'index** de PRISM se tient à jour ici, hors des requêtes : au plus toutes les :data:`INDEX_UPDATE_SECONDS`
  secondes une mise à jour part en arrière-plan (quelques secondes) ; sans index, la première plaque sans image
  trouvée par ses FDL lance sa construction (~2 minutes), une seule à la fois.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from urllib.parse import quote

from ...kernel import plugin_states
from ...kernel.errors import NotFound, Unavailable
from ..wafers.service import wafer_key
from . import source

logger = logging.getLogger(__name__)

LISTING_TTL = 600
LISTING_MEMO = 256
INDEX_UPDATE_SECONDS = 300

AREA_LABELS = {"Archive_Pollen": "Archive Pollen", "Datas_Automation_Pollen": "Automatisation Pollen", "Others": "Autres"}

_lock = threading.Lock()
# clé de plaque -> (lue à, liste rendue, {chemin relatif: chemin absolu})
_listings: dict[str, tuple[float, dict[str, Any], dict[str, str]]] = {}
_job: dict[str, Any] = {"running": False, "full": False, "started_at": None, "error": None}


def clean_fdls(values: Iterable[str | None]) -> list[str]:
    """Les FDL, sans vide ni doublon, dans l'ordre (PRISM ignore celles qui n'ont pas la forme ``2026-41155``)."""
    found: dict[str, None] = {}
    for value in values:
        text = " ".join(str(value or "").split())
        if text:
            found.setdefault(text[:40], None)
    return list(found)


# ── L'index de PRISM ──────────────────────────────────────────────────────────


def _run_index(full: bool) -> None:
    try:
        source.refresh_index(full=full)
        _job["error"] = None
    except Exception as exc:  # le partage a disparu, PRISM manque... : dit sur la page, jamais levé
        logger.warning("index des images MEB : %s", exc)
        _job["error"] = str(exc)
    finally:
        with _lock:
            _job.update(running=False, full=False)


def start_index(full: bool = False) -> bool:
    """Lance la construction (``full``) ou la mise à jour de l'index en arrière-plan ; ``False`` si une est déjà
    en cours."""
    with _lock:
        if _job["running"]:
            return False
        _job.update(running=True, full=full, started_at=time.time(), error=None)
    threading.Thread(target=_run_index, args=(full,), name="sem-images-index", daemon=True).start()
    return True


def maybe_update_index() -> None:
    """Une mise à jour en arrière-plan si l'index existe et date de plus de :data:`INDEX_UPDATE_SECONDS`."""
    age = source.index_age_seconds()
    if age is not None and age > INDEX_UPDATE_SECONDS:
        start_index(full=False)


def index_status() -> dict[str, Any]:
    """Où en est l'index : ce qu'en dit PRISM (``exists``, ``built_at``, ``checked_at``, ``wafers``...) et le
    travail en cours ici (``building`` : construction complète, ``updating`` : mise à jour, ``error``)."""
    info = source.index_info()
    with _lock:
        running, full, started, error = _job["running"], _job["full"], _job["started_at"], _job["error"]
    return {
        **{k: info.get(k) for k in ("exists", "built_at", "checked_at", "seconds", "folders", "wafers")},
        "building": running and (full or not info.get("exists")),
        "updating": running and not full and bool(info.get("exists")),
        "started_at": started if running else None,
        "error": error,
    }


# ── La liste d'une plaque ─────────────────────────────────────────────────────


def _relative(path: str, base: Path) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def _groups(rows: list[dict[str, Any]], base: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_folder: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    for row in rows:
        folder = row.get("folder") or ""
        group = by_folder.setdefault(folder, {
            "folder": folder, "area": row.get("area"), "area_label": AREA_LABELS.get(row.get("area") or "", row.get("area")),
            "lot": row.get("lot"), "fdl": row.get("fdl"), "process": row.get("process"), "step": row.get("step"), "images": [],
        })
        relative = _relative(row["path"], base)
        paths[relative] = row["path"]
        group["images"].append({
            "path": relative, "name": os.path.basename(row["path"]), "die": row.get("die"),
            "round": None if row.get("round") is None else int(row["round"]), "size": row.get("size"), "modified": row.get("modified"),
        })
    groups = []
    for group in by_folder.values():
        images = sorted(group["images"], key=lambda i: (i["die"] if i["die"] is not None else 1 << 30, i["round"] or 0, i["name"]))
        dates = sorted(d for d in (i["modified"] for i in images) if d)
        groups.append({**group, "images": images, "count": len(images),
                       "rounds": sorted({i["round"] for i in images if i["round"] is not None}),
                       "first": dates[0] if dates else None, "last": dates[-1] if dates else None})
    groups.sort(key=lambda g: g["last"] or "", reverse=True)
    return groups, paths


def listing(lasermark: str, fdls: Iterable[str | None], *, refresh: bool = False) -> dict[str, Any]:
    """Les images d'une plaque : ``groups`` (une acquisition chacune, la plus récente d'abord, ses ``images``),
    ``count``, ``fdls`` cherchées, ``read_at``, ``root`` et ``index`` (:func:`index_status`)."""
    key = wafer_key(lasermark)
    wanted = clean_fdls(fdls)
    now = time.time()
    with _lock:
        memo = _listings.get(key)
    if memo and not refresh and now - memo[0] < LISTING_TTL and memo[1]["fdls"] == wanted:
        return {**memo[1], "index": index_status()}

    base = source.require_root()
    maybe_update_index()
    rows = source.images(lasermark, wanted)
    groups, paths = _groups(rows, base)
    if not rows and not source.index_info().get("exists"):
        start_index(full=True)  # le partage n'a pas d'index : sans lui, une plaque sans FDL connue reste introuvable
    result = {"lasermark": lasermark, "fdls": wanted, "root": str(base), "groups": groups, "count": len(rows),
              "read_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + "+00:00"}
    with _lock:
        _listings[key] = (now, result, paths)
        while len(_listings) > LISTING_MEMO:
            _listings.pop(next(iter(_listings)))
    return {**result, "index": index_status()}


def image_path(lasermark: str, relative: str, fdls: Callable[[], Iterable[str | None]]) -> str:
    """Le fichier d'une image de la plaque, par son chemin relatif à la racine - seulement s'il est dans la liste
    de cette plaque (relue avec ``fdls()`` si elle a expiré : une vignette ne recalcule rien) : jamais un chemin
    quelconque."""
    key = wafer_key(lasermark)
    with _lock:
        memo = _listings.get(key)
    if memo is None or time.time() - memo[0] >= LISTING_TTL:
        listing(lasermark, fdls())
        with _lock:
            memo = _listings.get(key)
    path = memo[2].get(relative) if memo else None
    if not path:
        raise NotFound("Cette image n'est pas parmi les images MEB de la plaque.", code="sem_image_unknown")
    if not os.path.isfile(path):
        raise NotFound("Image introuvable : le fichier a été déplacé ou supprimé du partage.", code="sem_image_missing")
    return path


def url_for(lasermark: str, path: str, *, variant: str = "thumb", frame: int = 0) -> str | None:
    """L'adresse où un autre plugin (la fiche data, une analyse) montre une image du partage trouvée par le hook
    ``meb_g4`` pour cette plaque - son chemin absolu rendu relatif à la racine, servi par ``.../sem-images/file``
    comme les images de la page (seules celles de la liste de la plaque le sont). ``None`` : hors de la racine."""
    base = source.root()
    try:
        relative = _relative(path, base)
    except ValueError:  # un autre lecteur Windows
        return None
    if relative.startswith("..") or os.path.isabs(relative):
        return None
    query = f"path={quote(relative, safe='/')}&variant={variant}" + (f"&frame={frame}" if frame else "")
    return f"/api/wafers/{quote(lasermark, safe='')}/sem-images/file?{query}"


def image_urls(lasermark: str, path: str) -> tuple[str, str] | None:
    """(vignette, image entière) d'une image du partage pour la fiche data et les analyses (plugin wafer_data,
    ``register_image_server``) ; ``None`` quand ce plugin est désactivé, PRISM sans racine, ou le chemin hors racine."""
    if not plugin_states.is_enabled("sem_images"):
        return None
    try:
        thumb = url_for(lasermark, path)
    except Unavailable:
        return None
    return (thumb, url_for(lasermark, path, variant="view")) if thumb else None


def forget() -> None:
    """Oublie les listes gardées (tests)."""
    with _lock:
        _listings.clear()
