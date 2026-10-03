"""Les tables du plugin microprojects - µprojets, membres, invitations - et le renommage hérité
``project`` -> ``microproject``, qui touche aussi les tables du plugin links."""

from __future__ import annotations

import sqlite3

from ...kernel.db import column_names, data_dir, execute_script, rebuild_table, table_exists
from ...kernel.plugin import Migration
from ..accounts.security import hash_token
from ..areas.service import UNCLASSIFIED_AREA_SLUG
from .service import assign_code

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
    """Rename the pre-``microproject`` tables, columns and indexes, in place - and the on-disk half
    of the same rename: ``data/projects/`` holds one directory per µprojet (Follow repository,
    saved structures, step presets, attachments) and is now ``data/microprojects/``.

    The first migration of this plugin, so that it runs *before* any ``CREATE TABLE IF NOT
    EXISTS`` of a renamed table (``microprojects`` here, ``microproject_links`` in the links
    plugin, listed after this one): on an old database such a statement would happily create an
    empty ``microprojects`` alongside the populated ``projects`` and the rename would then be
    impossible. Each step is guarded independently, and the directory is left alone if the new one
    already exists - nothing here is allowed to merge two trees or overwrite live experiment history.
    """
    for old, new in _LEGACY_TABLE_RENAMES:
        if table_exists(conn, old) and not table_exists(conn, new):
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
    for table, old, new in _LEGACY_COLUMN_RENAMES:
        if table_exists(conn, table):
            columns = column_names(conn, table)
            if old in columns and new not in columns:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    for index in _LEGACY_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {index}")

    legacy = data_dir() / "projects"
    current = data_dir() / "microprojects"
    if legacy.is_dir() and not current.exists():
        legacy.rename(current)


SCHEMA = """
-- A "µprojet" in Spectre's vocabulary: one topic a management area addresses. The table, the
-- on-disk directory (``data/microprojects/<slug>``) and every internal identifier say
-- ``microproject``; only the French user-facing labels and URLs say "µprojet" / ``/microprojets``.
CREATE TABLE IF NOT EXISTS microprojects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    management_area_id INTEGER REFERENCES management_areas(id),
    thematic_id INTEGER REFERENCES thematics(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER NOT NULL REFERENCES users(id),
    -- its number, « Nat_0004 » = prefix + number: given once, when it first lands in a numbered
    -- corporate project, and kept for good (even if it moves) - see spectre.plugins.microprojects.service
    code_prefix TEXT,
    code_number INTEGER
);

CREATE TABLE IF NOT EXISTS memberships (
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (microproject_id, user_id)
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

CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_microproject ON invitations(microproject_id);
"""


def _initial(conn: sqlite3.Connection) -> None:
    """The tables, plus the columns a table written by an older Spectre doesn't have yet -
    ``CREATE ... IF NOT EXISTS`` never adds a column to a table that already exists."""
    execute_script(conn, SCHEMA)
    if "management_area_id" not in column_names(conn, "microprojects"):
        conn.execute("ALTER TABLE microprojects ADD COLUMN management_area_id INTEGER REFERENCES management_areas(id)")
    if "thematic_id" not in column_names(conn, "microprojects"):
        conn.execute("ALTER TABLE microprojects ADD COLUMN thematic_id INTEGER REFERENCES thematics(id) ON DELETE SET NULL")
    if "code_number" not in column_names(conn, "microprojects"):
        conn.execute("ALTER TABLE microprojects ADD COLUMN code_prefix TEXT")
        conn.execute("ALTER TABLE microprojects ADD COLUMN code_number INTEGER")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_microprojects_code ON microprojects(code_prefix, code_number) "
        "WHERE code_number IS NOT NULL"
    )


def _backfill_areas_and_codes(conn: sqlite3.Connection) -> None:
    """Every µprojet attached to a corporate project (« Non classé » for those that predate the
    strategy layer), and every µprojet already sitting in a numbered one given its number, in
    creation order - only what's still missing, never renumbering. « Non classé » has no prefix:
    its µprojets are numbered once attached to a real project."""
    area_id = conn.execute("SELECT id FROM management_areas WHERE slug = ?", (UNCLASSIFIED_AREA_SLUG,)).fetchone()["id"]
    conn.execute("UPDATE microprojects SET management_area_id = ? WHERE management_area_id IS NULL", (area_id,))
    pending = conn.execute(
        "SELECT microprojects.id, microprojects.management_area_id FROM microprojects "
        "JOIN management_areas ON management_areas.id = microprojects.management_area_id "
        "WHERE microprojects.code_number IS NULL AND management_areas.code_prefix != '' "
        "ORDER BY microprojects.created_at, microprojects.id"
    ).fetchall()
    for row in pending:
        assign_code(conn, row["id"], row["management_area_id"])


_INVITATIONS_WITH_ID = """
CREATE TABLE invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    microproject_id INTEGER NOT NULL REFERENCES microprojects(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
)
"""


def _invitation_ids_and_hashed_tokens(conn: sqlite3.Connection) -> None:
    """An invitation gets an id (what the members dialog cancels) and keeps only the SHA-256 of
    its token, like a session: the token in clear lives in the e-mail alone. The links already
    sent keep working - their token is hashed in place before the old column goes."""
    conn.execute("ALTER TABLE invitations ADD COLUMN token_hash TEXT")
    for row in conn.execute("SELECT rowid, token FROM invitations").fetchall():
        conn.execute("UPDATE invitations SET token_hash = ? WHERE rowid = ?", (hash_token(row["token"]), row["rowid"]))
    rebuild_table(conn, "invitations", _INVITATIONS_WITH_ID)


MIGRATIONS = (
    Migration("0001_legacy_project_rename", _rename_legacy_project_tables),
    Migration("0002_initial", _initial),
    Migration("0003_backfill_areas_and_codes", _backfill_areas_and_codes),
    Migration("0004_invitation_ids_and_hashed_tokens", _invitation_ids_and_hashed_tokens),
)
