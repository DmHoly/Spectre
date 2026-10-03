"""Le stockage du plugin intent_forms : des fichiers (bibliothèques JSON et ``commit_form.yml``),
aucune table. Les migrations reprennent les fichiers des versions précédentes."""

from __future__ import annotations

from ...kernel.plugin import Migration
from .service import migrate_legacy_files

MIGRATIONS = (Migration("0001_library_ids", migrate_legacy_files),)
