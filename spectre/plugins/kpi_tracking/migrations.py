"""La table du plugin kpi_tracking : les KPI suivis par projet corporate."""

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

# Le choix des KPI est celui du projet corporate, plus du µprojet : tous les µprojets du projet le
# partagent. La première version (par µprojet) n'a pas servi sur une instance : sa table est écartée.
PER_AREA = """
DROP TABLE IF EXISTS microproject_tracked_kpis;

-- Un KPI suivi par un projet corporate (spectre.plugins.kpi_tracking.service) : une colonne d'un type de
-- données PRISM (``hook`` + ``column_name``). Le projet ne garde que ce choix - les valeurs se calculent
-- à la demande sur les plaques de tous ses µprojets. ``label`` : un nom d'affichage libre (vide = la
-- colonne telle que PRISM la nomme).
CREATE TABLE IF NOT EXISTS area_tracked_kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE,
    hook TEXT NOT NULL,
    column_name TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (area_id, hook, column_name)
);

CREATE INDEX IF NOT EXISTS idx_area_tracked_kpis_area ON area_tracked_kpis(area_id, position);
"""


# Un KPI suit une colonne avec des filtres (``filters`` : une liste JSON de {column, op, value}, '[]' sans filtre) :
# la même colonne se suit plusieurs fois, avec des filtres différents - l'unicité porte donc sur les
# trois. SQLite ne change pas une contrainte en place : la table est refaite.
FILTERS = """
CREATE TABLE area_tracked_kpis_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE,
    hook TEXT NOT NULL,
    column_name TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    filters TEXT NOT NULL DEFAULT '[]',
    position INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (area_id, hook, column_name, filters)
);

INSERT INTO area_tracked_kpis_new (id, area_id, hook, column_name, label, position, created_by, created_at)
    SELECT id, area_id, hook, column_name, label, position, created_by, created_at FROM area_tracked_kpis;

DROP TABLE area_tracked_kpis;
ALTER TABLE area_tracked_kpis_new RENAME TO area_tracked_kpis;
CREATE INDEX IF NOT EXISTS idx_area_tracked_kpis_area ON area_tracked_kpis(area_id, position);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA), Migration("0002_per_area", PER_AREA), Migration("0003_filters", FILTERS))
