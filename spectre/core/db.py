"""SQLite storage for everything Follow and StructureForge don't model: accounts, projects,
membership. Deliberately the only relational piece of Spectre - both dependencies keep their own
data as flat JSON files (see ``follow.storage.backends.JsonFileStore`` and
``structureforge.core.recipe_store.RecipeStore``), and Spectre does not touch that; this module
only ever stores rows that need to be queried by something other than an id (an email, a project
membership).
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

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
"""


def data_dir() -> Path:
    """Where Spectre keeps everything it owns: the sqlite db, and one subdirectory per project
    holding that project's Follow repository and StructureForge recipe library. Overridable with
    ``SPECTRE_DATA_DIR`` (tests point this at a temp directory).
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
