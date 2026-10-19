"""Ce que PRISM sait des images MEB du G4 : le hook ``meb_g4`` (un TIF par die et par passe sur le partage
``PRISM_SEM_ROOT``, retrouvé par les FDL de la plaque ou par l'index des dossiers de PRISM) et cet index. PRISM
fournit la donnée ; ce plugin l'affiche. Ce module est le seul à importer ``prism`` ici."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from ...kernel.db import data_dir
from ...kernel.errors import Unavailable

HOOK = "meb_g4"


def _loader():
    # Le cache et l'index de PRISM vivent avec les données de Spectre (comme pour la caractérisation).
    os.environ.setdefault("PRISM_DATA_DIR", str(data_dir() / "prism"))
    try:
        from prism.loaders import meb_g4
    except ImportError as exc:
        raise Unavailable("PRISM n'est pas installé sur ce serveur : les images MEB ne se lisent pas.", code="prism_missing") from exc
    if not hasattr(meb_g4, "refresh_index"):
        raise Unavailable(
            "La version de PRISM installée ne sait pas encore chercher les images du G4 par FDL : mettez PRISM à jour.",
            code="prism_outdated",
        )
    return meb_g4


def root() -> Path:
    """La racine des images du G4 (``PRISM_SEM_ROOT``)."""
    _loader()
    from prism import settings

    return Path(settings.sem_root())


def require_root() -> Path:
    """La racine, si le partage est monté ; :class:`Unavailable` sinon - et toujours en démonstration
    (``SPECTRE_DEMO_DATA=1`` : aucune donnée réelle n'est lue, le partage non plus)."""
    if os.environ.get("SPECTRE_DEMO_DATA") == "1":
        raise Unavailable("Pas d'images MEB en démonstration : le partage n'est pas lu.", code="sem_demo")
    base = root()
    if not base.exists():
        raise Unavailable(f"Le partage des images MEB n'est pas accessible ({base}) : lecteur réseau non monté ?", code="sem_root_missing")
    return base


def images(lasermark: str, fdls: list[str]) -> list[dict[str, Any]]:
    """Les images d'une plaque (lignes du hook ``meb_g4``) : par ses ``fdls`` et par l'index s'il existe, lu tel
    quel (le service le tient à jour à part)."""
    _loader()
    require_root()
    import prism

    try:
        df = prism.run_hook(HOOK, wafer_names=[lasermark], fdl_numbers=fdls, update_index=False)
    except FileNotFoundError as exc:
        raise Unavailable(str(exc), code="sem_root_missing") from exc
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")


def index_info() -> dict[str, Any]:
    return _loader().index_info()


def refresh_index(full: bool = False) -> dict[str, Any]:
    return _loader().refresh_index(full=full)


def index_age_seconds() -> float | None:
    """Depuis quand l'index n'a pas été mis à jour (``None`` : pas d'index)."""
    loader = _loader()
    path = loader.index_path()
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None
