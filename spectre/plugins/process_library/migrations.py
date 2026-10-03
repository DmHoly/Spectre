"""Les bibliothèques sont des fichiers JSON (voir :mod:`.service`) : leurs migrations réécrivent ces
fichiers, pas des tables."""

from __future__ import annotations

import secrets
import sqlite3

from ...kernel.json_store import path_lock, read_json, write_json
from ...kernel.plugin import Migration
from .service import legacy_files


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


MIGRATIONS = (Migration("0001_item_ids", add_ids),)
