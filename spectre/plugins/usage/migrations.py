"""La table du plugin usage : les compteurs d'utilisation, agrégés par heure."""

from __future__ import annotations

from ...kernel.plugin import Migration

SCHEMA = """
-- How much an account used one route of one plugin during one hour (local time of the server):
-- the requests themselves are never kept, only these counters, added up by
-- ``usage.recorder`` every few seconds. ``kind`` is ``page`` (a page view) or ``api`` (a GET is a
-- read, anything else a write). No foreign key on ``user_id``: the history of a deleted account
-- stays in the totals.
CREATE TABLE IF NOT EXISTS usage_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    user_id INTEGER NOT NULL,
    plugin TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('api', 'page')),
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0,
    client_errors INTEGER NOT NULL DEFAULT 0,
    server_errors INTEGER NOT NULL DEFAULT 0,
    total_ms REAL NOT NULL DEFAULT 0,
    max_ms REAL NOT NULL DEFAULT 0,
    UNIQUE (day, hour, user_id, plugin, kind, method, route)
);

CREATE INDEX IF NOT EXISTS idx_usage_counts_user ON usage_counts(user_id, day);
CREATE INDEX IF NOT EXISTS idx_usage_counts_plugin ON usage_counts(plugin, day);
"""

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
