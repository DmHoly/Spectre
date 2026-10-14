"""Les tables du plugin teams : les équipes et leurs membres."""

from __future__ import annotations

import sqlite3

from ...kernel.db import column_names
from ...kernel.plugin import Migration

SCHEMA = """
-- A team: a group of accounts that owns corporate projects (management_areas.team_id, plugin
-- areas) and, through them, their µprojets. Created by an admin.
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Who is in a team: a ``manager`` has every right on what the team owns, a ``member`` only
-- belongs to it. An account may be in several teams, manager of some only.
CREATE TABLE IF NOT EXISTS team_members (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('manager', 'member')),
    PRIMARY KEY (team_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);
"""

# The badge colours teams start with, handed out in turn (the team's own choice replaces it).
PALETTE = ("#1f6feb", "#2da44e", "#d4571a", "#8250df", "#bf3989", "#0e8a9a", "#9a6700", "#cf222e")


def _badge(conn: sqlite3.Connection) -> None:
    """A team's badge: its colour and a short label (``''``: the initials of its name). Teams
    written before get a colour from the palette, by order of creation."""
    existing = column_names(conn, "teams")
    if "color" not in existing:
        conn.execute("ALTER TABLE teams ADD COLUMN color TEXT NOT NULL DEFAULT '#1f6feb'")
        for index, row in enumerate(conn.execute("SELECT id FROM teams ORDER BY id").fetchall()):
            conn.execute("UPDATE teams SET color = ? WHERE id = ?", (PALETTE[index % len(PALETTE)], row["id"]))
    if "badge" not in existing:
        conn.execute("ALTER TABLE teams ADD COLUMN badge TEXT NOT NULL DEFAULT ''")


MIGRATIONS = (Migration("0001_initial", SCHEMA), Migration("0002_badge", _badge))
