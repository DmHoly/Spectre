"""Les tables du plugin teams : les équipes et leurs membres."""

from __future__ import annotations

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

MIGRATIONS = (Migration("0001_initial", SCHEMA),)
