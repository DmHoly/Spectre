"""SQLite storage for everything Follow and StructureForge don't model: accounts, projects,
membership. Deliberately the only relational piece of Spectre - both dependencies (plus Spectre's
own libraries, e.g. ``spectre.core.step_presets.StepPresetStore``) keep their own data as flat
JSON files (see ``follow.storage.backends.JsonFileStore``), and Spectre does not touch that; this
module only ever stores rows that need to be queried by something other than an id (an email, a
project membership).
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
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS memberships (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE IF NOT EXISTS password_resets (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- Cross-project links (spectre.core.links) - the one relationship that reaches across two
-- projects' otherwise-isolated Follow repositories, so it lives here rather than as a Follow
-- reference (follow.core.models.ReferenceLink is validated to always point within its own
-- repository - see repository.py's own commit-time check) or in Experiment.metadata (which,
-- like physical_tracking, only one side could ever read).
CREATE TABLE IF NOT EXISTS project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_a_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    project_b_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (project_a_id <> project_b_id)
);

-- One physical entity is identified by (project, experience, index into that experience's
-- current physical_tracking list) - the same addressing the atlas already uses for its entity
-- nodes (entity:{experience_id}:{index}). Not a foreign key: the referenced experience lives in
-- a Follow repository, not this database, so nothing here can enforce it still exists - a link to
-- a since-deleted project or a physical_tracking entry that got reordered/removed by a later edit
-- is a stale row the atlas just quietly stops resolving, same as it already does for entities.
CREATE TABLE IF NOT EXISTS entity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a_project_slug TEXT NOT NULL,
    a_experience_id TEXT NOT NULL,
    a_entity_index INTEGER NOT NULL,
    b_project_slug TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_invitations_project ON invitations(project_id);
CREATE INDEX IF NOT EXISTS idx_project_links_a ON project_links(project_a_id);
CREATE INDEX IF NOT EXISTS idx_project_links_b ON project_links(project_b_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_a ON entity_links(a_project_slug);
CREATE INDEX IF NOT EXISTS idx_entity_links_b ON entity_links(b_project_slug);
"""


def data_dir() -> Path:
    """Where Spectre keeps everything it owns: the sqlite db, and one subdirectory per project
    holding that project's Follow repository and its saved structures/step presets. Overridable
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


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


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
