"""Les tables du plugin lots : lots de fabrication, leurs wafers et leurs thématiques visées."""

from __future__ import annotations

import sqlite3

from ...kernel.db import column_names, execute_script, rebuild_table
from ...kernel.plugin import Migration

SCHEMA = """
-- Suivi de lots (spectre.plugins.lots.service) : un lot de fabrication = des wafers (par lasermark),
-- une priorité (P10, P20...), un début, une fin prévisionnelle et une fin déclarée. Déclaratif pour
-- l'instant (source = 'declaratif') ; des datahooks l'alimenteront ensuite. Ses expériences ne sont
-- pas stockées ici : ce sont celles qui suivent ses wafers.
CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'wip', 'hold', 'done', 'cancelled')),
    started_on TEXT,
    forecast_exit_on TEXT,
    exited_on TEXT,
    hold_reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'declaratif',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lot_wafers (
    lot_id INTEGER NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    lasermark TEXT NOT NULL,
    lasermark_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (lot_id, lasermark_key)
);

CREATE TABLE IF NOT EXISTS lot_thematics (
    lot_id INTEGER NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    thematic_id INTEGER NOT NULL REFERENCES thematics(id) ON DELETE CASCADE,
    PRIMARY KEY (lot_id, thematic_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lots_code ON lots(code COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_lot_wafers_key ON lot_wafers(lasermark_key);
"""


def _initial(conn: sqlite3.Connection) -> None:
    execute_script(conn, SCHEMA)
    # un lot créé avec la toute première version du suivi de lots (parcours d'étapes, abandonné) :
    # la priorité arrive
    if "priority" not in column_names(conn, "lots"):
        conn.execute("ALTER TABLE lots ADD COLUMN priority TEXT NOT NULL DEFAULT ''")


LOTS_0003 = """
CREATE TABLE lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'wip', 'hold', 'done', 'cancelled')),
    started_on TEXT,
    forecast_exit_on TEXT,
    exited_on TEXT,
    hold_reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'declaratif' CHECK (source IN ('declaratif', 'prism')),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'))
)
"""


def _source_and_version(conn: sqlite3.Connection) -> None:
    """La source d'un lot n'accepte plus que ``declaratif`` (saisi à la main) ou ``prism`` (la base
    de production : priorité, dates et wafers en lecture seule) ; ``updated_at``, la version d'un
    lot (``If-Match``), s'écrit en ISO 8601 UTC, sans espace - un ``ETag`` n'en contient pas."""
    conn.execute("UPDATE lots SET source = 'declaratif' WHERE source NOT IN ('declaratif', 'prism')")
    rebuild_table(conn, "lots", LOTS_0003)
    conn.execute("UPDATE lots SET updated_at = replace(updated_at, ' ', 'T') || '+00:00' WHERE updated_at LIKE '% %'")


MIGRATIONS = (
    Migration("0001_initial", _initial),
    # la table des étapes de cette toute première version n'est plus lue
    Migration("0002_drop_lot_steps", "DROP TABLE IF EXISTS lot_steps;"),
    Migration("0003_source_and_version", _source_and_version),
)
