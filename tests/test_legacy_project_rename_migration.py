"""The ``project`` -> ``microproject`` rename is a pure naming change, but it has to be survivable:
a database and a ``data/`` tree written by an older Spectre must come back with every row and every
Follow repository intact. These tests build a genuine pre-rename installation by hand and then let
``init_db`` (plus the on-disk half of the migration) run over it.
"""

from __future__ import annotations

import sqlite3

# The schema exactly as Spectre wrote it before the rename - kept verbatim here rather than
# imported, so that a future edit to the current schema can never silently redefine what "the old
# shape" was.
LEGACY_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE management_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id)
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    management_area_id INTEGER REFERENCES management_areas(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE memberships (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE invitations (
    token TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    invited_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
CREATE TABLE project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_a_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    project_b_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (project_a_id <> project_b_id)
);
CREATE TABLE entity_links (
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
CREATE INDEX idx_invitations_project ON invitations(project_id);
CREATE INDEX idx_project_links_a ON project_links(project_a_id);
CREATE INDEX idx_project_links_b ON project_links(project_b_id);
CREATE INDEX idx_entity_links_a ON entity_links(a_project_slug);
CREATE INDEX idx_entity_links_b ON entity_links(b_project_slug);
"""


def seed_legacy_installation(data_dir):
    """A pre-rename ``data/`` directory: the old database with two µprojets, a membership, a
    pending invitation and both kinds of cross-µprojet link, plus the on-disk Follow repository
    that goes with one of them.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.executescript(LEGACY_SCHEMA)
    conn.executescript(
        """
        INSERT INTO users (id, email, name, password_hash, salt, is_admin)
            VALUES (1, 'chercheuse@exemple.fr', 'Chercheuse', 'hash', 'salt', 1),
                   (2, 'collegue@exemple.fr', 'Collegue', 'hash', 'salt', 0);
        INSERT INTO management_areas (id, slug, name) VALUES (1, 'nova-pt1', 'Nova (PT1)');
        INSERT INTO projects (id, slug, name, description, management_area_id, created_by)
            VALUES (1, 'nanofils-gan', 'Nanofils GaN', 'Epitaxie de reference', 1, 1),
                   (2, 'contact-ohmique', 'Contact ohmique', '', 1, 1);
        INSERT INTO memberships (project_id, user_id, role)
            VALUES (1, 1, 'owner'), (1, 2, 'editor'), (2, 1, 'owner');
        INSERT INTO invitations (token, project_id, email, role, invited_by, expires_at)
            VALUES ('tok', 1, 'invite@exemple.fr', 'viewer', 1, '2099-01-01T00:00:00');
        INSERT INTO project_links (id, project_a_id, project_b_id, note, created_by)
            VALUES (1, 1, 2, 'meme plaque de depart', 1);
        INSERT INTO entity_links
            (a_project_slug, a_experience_id, a_entity_index,
             b_project_slug, b_experience_id, b_entity_index, note, created_by)
            VALUES ('nanofils-gan', 'exp-a', 0, 'contact-ohmique', 'exp-b', 1, 'meme wafer', 1);
        """
    )
    conn.commit()
    conn.close()

    repo = data_dir / "projects" / "nanofils-gan" / "follow"
    repo.mkdir(parents=True)
    (repo / "experiments.json").write_text('{"kept": true}', encoding="utf-8")


def test_legacy_database_and_data_dir_are_renamed_in_place(data_dir):
    seed_legacy_installation(data_dir)

    from spectre.core import db

    db.init_db()

    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.row_factory = sqlite3.Row

    # Every row survived, under the new names.
    slugs = [r["slug"] for r in conn.execute("SELECT slug FROM microprojects ORDER BY id")]
    assert slugs == ["nanofils-gan", "contact-ohmique"]
    roles = conn.execute(
        "SELECT role FROM memberships WHERE microproject_id = 1 ORDER BY user_id"
    ).fetchall()
    assert [r["role"] for r in roles] == ["owner", "editor"]
    assert conn.execute("SELECT microproject_id FROM invitations").fetchone()["microproject_id"] == 1
    link = conn.execute("SELECT * FROM microproject_links").fetchone()
    assert (link["microproject_a_id"], link["microproject_b_id"]) == (1, 2)
    entity = conn.execute("SELECT * FROM entity_links").fetchone()
    assert entity["a_microproject_slug"] == "nanofils-gan"
    assert entity["b_microproject_slug"] == "contact-ohmique"

    # The old table names are gone rather than left behind as empty duplicates - the trap being
    # that ``_SCHEMA``'s CREATE ... IF NOT EXISTS would happily create one if the rename ran late.
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "projects" not in tables
    assert "project_links" not in tables

    # Indexes: the renamed ones are gone, the ones that kept their name still point at the
    # renamed columns (SQLite rewrites those itself).
    indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"idx_invitations_project", "idx_project_links_a", "idx_project_links_b"} & indexes == set()
    assert {"idx_invitations_microproject", "idx_entity_links_a", "idx_entity_links_b"} <= indexes
    conn.close()

    # The on-disk half: the Follow repository moved with its µprojet, contents untouched.
    assert not (data_dir / "projects").exists()
    moved = data_dir / "microprojects" / "nanofils-gan" / "follow" / "experiments.json"
    assert moved.read_text(encoding="utf-8") == '{"kept": true}'


def test_migrated_installation_is_readable_through_the_normal_code_path(data_dir):
    """Not just the right column names - the ordinary data-access layer finds the migrated rows."""
    seed_legacy_installation(data_dir)

    from spectre.core import db, microprojects, permissions

    db.init_db()

    microproject = microprojects.get_by_slug("nanofils-gan")
    assert microproject.name == "Nanofils GaN"
    assert permissions.role_for(microproject.id, user_id=2) == "editor"
    assert {p.slug: role for p, role in microprojects.list_for_user(1)} == {"nanofils-gan": "owner", "contact-ohmique": "owner"}


def test_migration_is_idempotent_and_leaves_a_current_database_alone(data_dir):
    """Running twice must be a no-op, and so must running against a database that never had the
    old names - the guards are per-step, so a start-up interrupted halfway also finishes cleanly.
    """
    seed_legacy_installation(data_dir)

    from spectre.core import db, microprojects

    db.init_db()
    db.init_db()

    assert {p.slug: role for p, role in microprojects.list_for_user(1)} == {"nanofils-gan": "owner", "contact-ohmique": "owner"}
    assert (data_dir / "microprojects" / "nanofils-gan" / "follow" / "experiments.json").exists()
