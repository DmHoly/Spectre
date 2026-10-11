"""Les tables du plugin references : les références de structure (un objet de toute l'application),
leurs versions et les slugs des références retirées (jamais redonnés). Les refs locales d'avant
ont été regroupées une fois par la migration 0005 (``local_refs``), qui a ensuite supprimé les
tables qui suivaient ce regroupement (µprojets lus, règle passée, étiquettes écartées par un admin).

``structure_references`` plutôt que ``references`` : ``REFERENCES`` est un mot réservé de SQL."""

from __future__ import annotations

import sqlite3

from ...kernel.plugin import Migration
from .local_refs import import_shared_local_refs

SCHEMA = """
-- Une référence de structure : un point de départ réutilisé dans plusieurs µprojets. Son slug est
-- fixé à la création (une étude cite sa référence par lui : reference_origin) ; son nom se renomme.
CREATE TABLE IF NOT EXISTS structure_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL
);

-- Une version d'une référence : MAJEUR.MINEUR calculé (service.next_number), la version de
-- référence dont elle dérive, sa source (µprojet, piste, version Follow ; la ref locale dont elle
-- vient pour une version importée) et l'instantané de la structure (JSON), qui la rend utilisable
-- même si l'étude source disparaît ou change de droits.
CREATE TABLE IF NOT EXISTS reference_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id INTEGER NOT NULL REFERENCES structure_references(id) ON DELETE CASCADE,
    number_major INTEGER NOT NULL,
    number_minor INTEGER NOT NULL,
    parent_version_id INTEGER REFERENCES reference_versions(id) ON DELETE SET NULL,
    parent_inferred INTEGER NOT NULL DEFAULT 0,
    microproject_id INTEGER REFERENCES microprojects(id) ON DELETE SET NULL,
    microproject_name TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    local_tag TEXT,
    snapshot TEXT NOT NULL,
    change_level TEXT NOT NULL CHECK (change_level IN ('initial', 'major', 'minor', 'patch', 'none')),
    note TEXT NOT NULL DEFAULT '',
    published_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    published_at TEXT NOT NULL,
    UNIQUE (reference_id, number_major, number_minor)
);

CREATE INDEX IF NOT EXISTS idx_reference_versions_source ON reference_versions(microproject_id, version_id);

-- Les µprojets dont les refs locales ont été lues (local_refs.import_local_refs) - relus quand leurs
-- étiquettes nommées changent (tags_fingerprint, migration 0004).
CREATE TABLE IF NOT EXISTS reference_import_scans (
    microproject_id INTEGER PRIMARY KEY REFERENCES microprojects(id) ON DELETE CASCADE,
    scanned_at TEXT NOT NULL
);
"""

RETIRED_SLUGS = """
-- Les slugs des références retirées qui avaient des versions : jamais redonnés (service._unique_slug),
-- pour que les études parties d'une version retirée ne passent pas à une autre référence du même nom.
CREATE TABLE IF NOT EXISTS retired_reference_slugs (
    slug TEXT PRIMARY KEY,
    retired_at TEXT NOT NULL
);
"""

IMPORT_RULES = """
-- Les règles de regroupement des refs locales déjà passées (local_refs.RULE) : la règle du
-- 2026-10-05 (seuls les noms présents dans au moins deux µprojets deviennent des références) retire
-- une fois ce que l'ancienne avait importé d'un seul µprojet, puis relit tous les µprojets.
CREATE TABLE IF NOT EXISTS reference_import_rules (
    rule TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

DISMISSED_TAGS = """
-- L'empreinte des étiquettes nommées d'un µprojet à sa dernière lecture (local_refs._fingerprint) :
-- le regroupement repasse quand elle change (une ref posée, retirée ou déplacée dans un µprojet lu).
ALTER TABLE reference_import_scans ADD COLUMN tags_fingerprint TEXT NOT NULL DEFAULT '';

-- Les étiquettes (µprojet, nom) dont la référence où elles avaient été importées a été retirée
-- (service.delete_reference) : le regroupement ne les relit plus, le retrait reste définitif.
CREATE TABLE IF NOT EXISTS dismissed_local_refs (
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    local_tag TEXT NOT NULL,
    dismissed_at TEXT NOT NULL,
    PRIMARY KEY (microproject_id, local_tag)
);
"""

TRACKING_TABLES = ("reference_import_scans", "reference_import_rules", "dismissed_local_refs")


def _local_refs_imported_once(conn: sqlite3.Connection) -> None:
    """Le dernier regroupement des refs locales (:func:`local_refs.import_shared_local_refs`) : plus
    rien ne pose d'étiquette Follow depuis les refs déclarées, le regroupement ne trouverait plus
    jamais rien - avant, chaque lecture des références rebalayait tous les µprojets. Puis les tables
    qui le suivaient (:data:`TRACKING_TABLES`) sont supprimées."""
    import_shared_local_refs(conn)
    for table in TRACKING_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


MIGRATIONS = (
    Migration("0001_initial", SCHEMA),
    Migration("0002_retired_slugs", RETIRED_SLUGS),
    Migration("0003_import_rules", IMPORT_RULES),
    Migration("0004_dismissed_local_refs", DISMISSED_TAGS),
    Migration("0005_local_refs_imported_once", _local_refs_imported_once),
)
