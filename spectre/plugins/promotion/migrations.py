"""La table du plugin promotion : le journal des promotions - qui a choisi quelle structure comme
référence, pourquoi, et ce que disaient les règles ce jour-là."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Une promotion : une structure (une version d'étude, une variante pour un split) devenue une
-- version de référence. Les noms sont gardés tels qu'à la promotion (la référence ou le µprojet
-- peuvent être renommés ou retirés ensuite) ; verdicts : les règles passées (JSON,
-- [{rule, label, level, message, code}]), pour relire plus tard sous quelles règles on a choisi.
CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id INTEGER REFERENCES structure_references(id) ON DELETE SET NULL,
    reference_version_id INTEGER REFERENCES reference_versions(id) ON DELETE SET NULL,
    reference_slug TEXT NOT NULL,
    reference_name TEXT NOT NULL,
    number TEXT NOT NULL,
    created_reference INTEGER NOT NULL DEFAULT 0,
    microproject_id INTEGER REFERENCES microprojects(id) ON DELETE SET NULL,
    microproject_name TEXT NOT NULL DEFAULT '',
    experiment_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    variant INTEGER,
    study_title TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    verdicts TEXT NOT NULL DEFAULT '[]',
    promoted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    promoted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_promotions_source ON promotions(microproject_id, experiment_id);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
