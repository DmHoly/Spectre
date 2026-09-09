"""SQLite storage for everything Follow and StructureForge don't model: accounts, microprojects,
membership. Deliberately the only relational piece of Spectre - both dependencies (plus Spectre's
own libraries, e.g. ``spectre.core.step_presets.StepPresetStore``) keep their own data as flat
JSON files (see ``follow.storage.backends.JsonFileStore``), and Spectre does not touch that; this
module only ever stores rows that need to be queried by something other than an id (an email, a
microproject membership).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Corporate strategy layer above the µprojets: the "grands thèmes" leadership steers by. A µprojet
-- (the ``microprojects`` table below - Spectre's URLs/labels call it "µprojet") belongs to exactly one
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
    created_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- A "µprojet" in Spectre's vocabulary: one topic a management area addresses. The table, the
-- on-disk directory (``data/microprojects/<slug>``) and every internal identifier say
-- ``microproject``; only the French user-facing labels and URLs say "µprojet" / ``/microprojets``.
CREATE TABLE IF NOT EXISTS microprojects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    management_area_id INTEGER REFERENCES management_areas(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS memberships (
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (microproject_id, user_id)
);

CREATE TABLE IF NOT EXISTS password_resets (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- Cross-microproject links (spectre.core.links) - the one relationship that reaches across two
-- microprojects' otherwise-isolated Follow repositories, so it lives here rather than as a Follow
-- reference (follow.core.models.ReferenceLink is validated to always point within its own
-- repository - see repository.py's own commit-time check) or in Experiment.metadata (which,
-- like physical_tracking, only one side could ever read).
CREATE TABLE IF NOT EXISTS microproject_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microproject_a_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    microproject_b_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (microproject_a_id <> microproject_b_id)
);

-- One physical entity is identified by (microproject, experience, index into that experience's
-- current physical_tracking list) - the same addressing the atlas already uses for its entity
-- nodes (entity:{experience_id}:{index}). Not a foreign key: the referenced experience lives in
-- a Follow repository, not this database, so nothing here can enforce it still exists - a link to
-- a since-deleted microproject or a physical_tracking entry that got reordered/removed by a later edit
-- is a stale row the atlas just quietly stops resolving, same as it already does for entities.
CREATE TABLE IF NOT EXISTS entity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a_microproject_slug TEXT NOT NULL,
    a_experience_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_microproject_slug TEXT NOT NULL,
    b_experience_id TEXT NOT NULL,
    b_entity_index INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_microproject ON invitations(microproject_id);
CREATE INDEX IF NOT EXISTS idx_microproject_links_a ON microproject_links(microproject_a_id);
CREATE INDEX IF NOT EXISTS idx_microproject_links_b ON microproject_links(microproject_b_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_a ON entity_links(a_microproject_slug);
CREATE INDEX IF NOT EXISTS idx_entity_links_b ON entity_links(b_microproject_slug);
"""


def data_dir() -> Path:
    """Where Spectre keeps everything it owns: the sqlite db, and one subdirectory per microproject
    holding that microproject's Follow repository and its saved structures/step presets. Overridable
    with ``SPECTRE_DATA_DIR`` (tests point this at a temp directory).
    """
    path = Path(os.environ.get("SPECTRE_DATA_DIR", "data")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "spectre.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


UNCLASSIFIED_AREA_SLUG = "non-classe"


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


# ``project`` -> ``microproject``: the entity has been called a "µprojet" in the UI, the URLs and
# the API for a while, and the internals finally follow. Purely a naming change - no column gained,
# lost or changed meaning - so a database written by an older Spectre migrates in place.
_LEGACY_TABLE_RENAMES = (
    ("projects", "microprojects"),
    ("project_links", "microproject_links"),
)
_LEGACY_COLUMN_RENAMES = (
    ("memberships", "project_id", "microproject_id"),
    ("invitations", "project_id", "microproject_id"),
    ("microproject_links", "project_a_id", "microproject_a_id"),
    ("microproject_links", "project_b_id", "microproject_b_id"),
    ("entity_links", "a_project_slug", "a_microproject_slug"),
    ("entity_links", "b_project_slug", "b_microproject_slug"),
)
# Only the indexes whose *name* changed: SQLite rewrites an index's column references itself on
# RENAME COLUMN, so ``idx_entity_links_a``/``_b`` keep working and stay as they are.
_LEGACY_INDEXES = ("idx_invitations_project", "idx_project_links_a", "idx_project_links_b")


def _rename_legacy_project_tables(conn: sqlite3.Connection) -> None:
    """Rename the pre-``microproject`` tables, columns and indexes, in place.

    Must run *before* ``_SCHEMA``: that script only ``CREATE ... IF NOT EXISTS``, so on an old
    database it would happily create an empty ``microprojects`` alongside the populated
    ``projects`` and the rename would then be impossible. Each step is guarded independently
    rather than behind one "is this an old database" flag, so a half-applied migration (an
    interrupted start-up) finishes cleanly on the next run.
    """
    for old, new in _LEGACY_TABLE_RENAMES:
        if _table_exists(conn, old) and not _table_exists(conn, new):
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
    for table, old, new in _LEGACY_COLUMN_RENAMES:
        if _table_exists(conn, table):
            columns = _column_names(conn, table)
            if old in columns and new not in columns:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    for index in _LEGACY_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {index}")


def _rename_legacy_project_dir() -> None:
    """The on-disk half of the same rename: ``data/projects/`` holds one directory per µprojet
    (Follow repository, saved structures, step presets, attachments) and is now
    ``data/microprojects/``. Left alone if the new directory already exists - nothing here is
    allowed to merge two trees or overwrite live experiment history.
    """
    legacy = data_dir() / "projects"
    current = data_dir() / "microprojects"
    if legacy.is_dir() and not current.exists():
        legacy.rename(current)


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing database up to the current schema. ``_SCHEMA`` above only ever
    ``CREATE ... IF NOT EXISTS``, so a table that already exists never picks up a new column - that
    is what this does, plus the one-time data backfill the management layer needs (a catch-all
    area, every µprojet attached to one, the first account made admin).
    """
    if "is_admin" not in _column_names(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "management_area_id" not in _column_names(conn, "microprojects"):
        conn.execute("ALTER TABLE microprojects ADD COLUMN management_area_id INTEGER REFERENCES management_areas(id)")

    if conn.execute("SELECT 1 FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)).fetchone() is None:
        conn.execute(
            "INSERT INTO management_areas (slug, name, description) VALUES (?, 'Non classé', ?)",
            (UNCLASSIFIED_AREA_SLUG, "µprojets pas encore rattachés à un grand thème."),
        )
    area_id = conn.execute("SELECT id FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)).fetchone()["id"]
    conn.execute("UPDATE microprojects SET management_area_id = ? WHERE management_area_id IS NULL", (area_id,))

    # Seed the three flagship themes on a fresh instance - only when no real theme exists yet
    # (never re-added once someone has created / renamed / removed one).
    real_themes = conn.execute(
        "SELECT COUNT(*) AS n FROM management_areas WHERE slug != ?", (UNCLASSIFIED_AREA_SLUG,)
    ).fetchone()["n"]
    if real_themes == 0:
        for slug, name in (("datacom-vlc", "Datacom (VLC)"), ("nova-pt1", "Nova (PT1)"), ("native-pt2", "Native (PT2)")):
            conn.execute("INSERT INTO management_areas (slug, name) VALUES (?, ?)", (slug, name))

    has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    has_admin = conn.execute("SELECT 1 FROM users WHERE is_admin = 1 LIMIT 1").fetchone() is not None
    if has_users and not has_admin:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)")


def init_db() -> None:
    with connect() as conn:
        _rename_legacy_project_tables(conn)
        conn.executescript(_SCHEMA)
        _migrate(conn)
    _rename_legacy_project_dir()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """One connection, committed on success and always closed - the standard shape for a request
    handler that both reads and writes in the same call.
    """
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
