"""La table du plugin kpi_tracking : les KPI suivis par µprojet."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- Un KPI suivi par un µprojet (spectre.plugins.kpi_tracking.service) : une colonne d'un type de données
-- PRISM (``hook`` + ``column``, voir le catalogue de characterization). Le µprojet ne garde que ce choix -
-- les valeurs se calculent à la demande sur les plaques qu'il suit, jamais copiées ici. ``label`` : un
-- nom d'affichage libre (vide = la colonne telle que PRISM la nomme).
CREATE TABLE IF NOT EXISTS microproject_tracked_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    hook TEXT NOT NULL,
    column_name TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (microproject_id, hook, column_name)
);

CREATE INDEX IF NOT EXISTS idx_tracked_kpis_microproject ON microproject_tracked_kpis(microproject_id, position);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
