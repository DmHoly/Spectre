"""Les tables du plugin areas - projets corporate, thématiques, objectifs - et les projets de départ
d'une instance neuve."""

from __future__ import annotations

import sqlite3

from ...kernel.db import column_names, execute_script, rebuild_table
from ...kernel.plugin import Migration
from .service import UNCLASSIFIED_AREA_SLUG, derive_code_prefix

SCHEMA = """
-- Corporate strategy layer, top of the three-level hierarchy: the "projets corporate" leadership
-- steers by (Native (PT2), VLC (microlink), Nova (PT1)). Under each sit its thématiques
-- (``thematics``), and under those the µprojets (``microprojects``). A µprojet belongs to exactly one
-- area; the seeded "non-classe" area holds anything not yet sorted. Visible to every signed-in
-- user (company-wide overview); only an admin (users.is_admin) creates/renames one or moves a
-- µprojet between areas.
CREATE TABLE IF NOT EXISTS management_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id),
    objectives_period TEXT NOT NULL DEFAULT '6 prochains mois',
    -- prefix of the numbers its µprojets get (« Nat » -> Nat_0001, Nat_0002...); '' = not numbered
    code_prefix TEXT NOT NULL DEFAULT ''
);

-- Middle level: a technical thématique of one corporate project (dopage PGaN, double EBL...). It
-- groups the µprojets - chains of experiments - that address it. Slug unique within its area only.
CREATE TABLE IF NOT EXISTS thematics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    management_area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id),
    UNIQUE (management_area_id, slug)
);

-- A corporate project's objectives for the coming period. ``weight`` is a figure (0-100 %) used to
-- compute the team's bonus - only recorded and shown, and objectives are ranked by it; ``position``
-- only orders objectives without one (0 = most important). ``achieved`` + the µprojet that
-- validated it say whether it was reached, and by whom.
CREATE TABLE IF NOT EXISTS area_objectives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    management_area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    weight REAL,
    achieved INTEGER NOT NULL DEFAULT 0,
    validated_by_microproject_id INTEGER REFERENCES microprojects(id) ON DELETE SET NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_thematics_area ON thematics(management_area_id);
CREATE INDEX IF NOT EXISTS idx_area_objectives_area ON area_objectives(management_area_id);
"""


def _initial(conn: sqlite3.Connection) -> None:
    """The tables, plus the columns a table written by an older Spectre doesn't have yet -
    ``CREATE ... IF NOT EXISTS`` never adds a column to a table that already exists."""
    execute_script(conn, SCHEMA)
    if "objectives_period" not in column_names(conn, "management_areas"):
        conn.execute("ALTER TABLE management_areas ADD COLUMN objectives_period TEXT NOT NULL DEFAULT '6 prochains mois'")
    if "weight" not in column_names(conn, "area_objectives"):
        conn.execute("ALTER TABLE area_objectives ADD COLUMN weight REAL")
    if "achieved" not in column_names(conn, "area_objectives"):
        conn.execute("ALTER TABLE area_objectives ADD COLUMN achieved INTEGER NOT NULL DEFAULT 0")
    if "validated_by_microproject_id" not in column_names(conn, "area_objectives"):
        conn.execute(
            "ALTER TABLE area_objectives ADD COLUMN validated_by_microproject_id INTEGER "
            "REFERENCES microprojects(id) ON DELETE SET NULL"
        )
    if "code_prefix" not in column_names(conn, "management_areas"):
        conn.execute("ALTER TABLE management_areas ADD COLUMN code_prefix TEXT NOT NULL DEFAULT ''")


_FLAGSHIP_PREFIXES = (("native-pt2", "Nat"), ("nova-pt1", "Nov"), ("datacom-vlc", "VLC"))


def _seed(conn: sqlite3.Connection) -> None:
    """The catch-all « Non classé » area; the three corporate projects on a fresh instance - only
    when no real theme exists yet (never re-added once someone has created / renamed / removed
    one); and every corporate project's code prefix (the flagship ones their usual « Nat »/« Nov »/
    « VLC », any other one derived from its name) - only what's still missing."""
    if conn.execute("SELECT 1 FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)).fetchone() is None:
        conn.execute(
            "INSERT INTO management_areas (slug, name, description) VALUES (?, 'Non classé', ?)",
            (UNCLASSIFIED_AREA_SLUG, "µprojets pas encore rattachés à un projet corporate."),
        )
    real_themes = conn.execute(
        "SELECT COUNT(*) AS n FROM management_areas WHERE slug != ?", (UNCLASSIFIED_AREA_SLUG,)
    ).fetchone()["n"]
    if real_themes == 0:
        for slug, name in (("native-pt2", "Native (PT2)"), ("datacom-vlc", "VLC (microlink)"), ("nova-pt1", "Nova (PT1)")):
            conn.execute("INSERT INTO management_areas (slug, name) VALUES (?, ?)", (slug, name))
    # The VLC project's first seeded name; only renamed if nobody has renamed it since.
    conn.execute("UPDATE management_areas SET name = 'VLC (microlink)' WHERE slug = 'datacom-vlc' AND name = 'Datacom (VLC)'")

    for slug, prefix in _FLAGSHIP_PREFIXES:
        conn.execute("UPDATE management_areas SET code_prefix = ? WHERE slug = ? AND code_prefix = ''", (prefix, slug))
    unprefixed = conn.execute(
        "SELECT id, name FROM management_areas WHERE code_prefix = '' AND slug != ?", (UNCLASSIFIED_AREA_SLUG,)
    ).fetchall()
    for row in unprefixed:
        taken = {r["code_prefix"].lower() for r in conn.execute("SELECT code_prefix FROM management_areas") if r["code_prefix"]}
        conn.execute("UPDATE management_areas SET code_prefix = ? WHERE id = ?", (derive_code_prefix(row["name"], taken), row["id"]))


def _team(conn: sqlite3.Connection) -> None:
    """The team that owns a corporate project (plugin teams). Nothing is attached: until an admin
    attaches the projects to teams, the rights stay what they were (only an admin writes)."""
    if "team_id" not in column_names(conn, "management_areas"):
        conn.execute("ALTER TABLE management_areas ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_management_areas_team ON management_areas(team_id)")


_AREAS_WITHOUT_TEAM = """
CREATE TABLE management_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id),
    objectives_period TEXT NOT NULL DEFAULT '6 prochains mois',
    code_prefix TEXT NOT NULL DEFAULT ''
)
"""


def _teams_per_area(conn: sqlite3.Connection) -> None:
    """Several teams work in one corporate project, and a thématique belongs to one of them.

    - ``area_teams``: the teams that work in a project (replaces the single ``management_areas.team_id``,
      whose value becomes the first row);
    - ``thematics.team_id``: the team that owns a thématique - the one its project had until now.
      No team (``NULL``): an open thématique, seen by everyone and written by the project's managers;
    - ``thematic_teams``: the teams invited into a thématique - they read it and its µprojets.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS area_teams ("
        "management_area_id INTEGER NOT NULL REFERENCES management_areas(id) ON DELETE CASCADE, "
        "team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, "
        "PRIMARY KEY (management_area_id, team_id))"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_area_teams_team ON area_teams(team_id)")
    if "team_id" not in column_names(conn, "thematics"):
        conn.execute("ALTER TABLE thematics ADD COLUMN team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thematics_team ON thematics(team_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS thematic_teams ("
        "thematic_id INTEGER NOT NULL REFERENCES thematics(id) ON DELETE CASCADE, "
        "team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE, "
        "PRIMARY KEY (thematic_id, team_id))"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thematic_teams_team ON thematic_teams(team_id)")
    if "team_id" in column_names(conn, "management_areas"):
        conn.execute(
            "INSERT OR IGNORE INTO area_teams (management_area_id, team_id) "
            "SELECT id, team_id FROM management_areas WHERE team_id IS NOT NULL"
        )
        conn.execute(
            "UPDATE thematics SET team_id = (SELECT team_id FROM management_areas WHERE id = thematics.management_area_id) "
            "WHERE team_id IS NULL"
        )
        conn.execute("DROP INDEX IF EXISTS idx_management_areas_team")
        rebuild_table(conn, "management_areas", _AREAS_WITHOUT_TEAM)  # DROP COLUMN refuses a column with a foreign key


MIGRATIONS = (
    Migration("0001_initial", _initial),
    Migration("0002_seed", _seed),
    Migration("0003_team", _team),
    Migration("0004_teams_per_area", _teams_per_area),
)
