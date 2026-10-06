"""Les bibliothèques sont des fichiers JSON (voir :mod:`.service`) : leurs migrations réécrivent ces
fichiers, pas des tables."""

from __future__ import annotations

import hashlib
import secrets
import shutil
import sqlite3
from pathlib import Path

from ...kernel.json_store import path_lock, read_json, write_json
from ...kernel.plugin import Migration
from ..library import service as library
from .service import legacy_files
from .step_presets import legacy_step


def add_ids(conn: sqlite3.Connection | None = None) -> None:
    """Ancien format ``{"structures": {nom: élément}}`` -> ``{"items": [élément, ...]}`` : chaque
    élément reçoit un ``id`` opaque, et un auteur inconnu (``created_by`` / ``updated_by`` à
    ``None``) - un élément partagé sans auteur n'est donc plus modifiable que par un administrateur.
    Un fichier déjà migré est laissé tel quel : la migration peut reprendre après une interruption."""
    for path, legacy_key in legacy_files():
        with path_lock(path):
            data = read_json(path, strict=True)
            if "items" in data:
                continue
            legacy = data.get(legacy_key) or {}
            items = [
                {**raw, "id": secrets.token_hex(8), "created_by": None, "updated_by": None}
                for raw in legacy.values()
                if isinstance(raw, dict)
            ]
            write_json(path, {"items": items})


def _step_preset_files() -> list:
    return [path for path, key in legacy_files() if key == "presets"]


def whole_step_presets(conn: sqlite3.Connection | None = None) -> None:
    """Un préset d'étape est désormais une étape entière (``step``), et plus seulement le nom d'une
    recette (``payload`` : ``{kind, recipe}``) : chaque préset de l'ancienne forme devient une étape
    de ce type qui nomme cette recette, avec les valeurs par défaut du constructeur pour le reste
    (un dépôt de 20 nm de SiO2, une gravure de 10 nm). Un préset déjà converti est laissé tel quel."""
    for path in _step_preset_files():
        with path_lock(path):
            data = read_json(path, strict=True)
            items = data.get("items") if isinstance(data.get("items"), list) else []
            changed = False
            for raw in items:
                payload = raw.get("payload") if isinstance(raw, dict) else None
                if not isinstance(payload, dict) or "step" in raw:
                    continue
                raw.pop("payload")
                raw["step"] = legacy_step(raw.get("name") or "Étape", payload.get("kind", ""), payload.get("recipe") or "")
                changed = True
            if changed:
                write_json(path, {**data, "items": items})


# l'empreinte (sha256, fins de ligne normalisées) des presets.yml livrés avant les présets d'étape
# entiers : un fichier de l'instance encore identique à l'un d'eux n'a jamais été édité
_SHIPPED_RECIPE_ONLY_PRESETS = {
    "b0d1179698b09f455c2c97afd50e4f02836ff27e01ec2088cb530ab34989e4a5",
    "ad53aab3aeeb16952ff3441ce5f805900733de6f54539ea8485daad40204227e",
}


def _active_presets_file() -> list[Path]:
    path = library.library_dir() / "presets.yml"
    return [path] if path.is_file() else []


def ship_whole_step_presets(conn: sqlite3.Connection | None = None) -> None:
    """Le ``presets.yml`` de l'instance, s'il est encore celui livré avant les présets d'étape
    entiers (jamais édité), est remplacé par le nouveau fichier livré - une version éditée est
    laissée telle quelle (ses présets, qui ne nomment qu'une recette, restent lus)."""
    for path in _active_presets_file():
        text = path.read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(text).hexdigest() in _SHIPPED_RECIPE_ONLY_PRESETS:
            shutil.copyfile(library.DEFAULTS_DIR / "presets.yml", path)


MIGRATIONS = (
    Migration("0001_item_ids", add_ids, files=lambda: [path for path, _key in legacy_files()]),
    Migration("0002_whole_step_presets", whole_step_presets, files=_step_preset_files),
    Migration("0003_ship_whole_step_presets", ship_whole_step_presets, files=_active_presets_file),
)
