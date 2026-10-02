"""Le passage de ``init_db()`` (un seul script, rejoué à chaque démarrage) aux migrations versionnées
des plugins : une base écrite par l'ancien code reprend exactement le schéma d'une base neuve, chaque
migration ne s'applique qu'une fois - et l'exécuteur lui-même (transaction par migration, script
découpé instruction par instruction, reconstruction d'une table).
"""

from __future__ import annotations

import sqlite3

import pytest

from spectre.kernel.db import connect, execute_script, rebuild_table, run_migrations
from spectre.kernel.plugin import Migration, Plugin

# Le schéma tel que l'écrivait ``spectre.core.db`` à 03f4646, recopié plutôt qu'importé : une
# modification future des migrations ne peut pas redéfinir en silence ce qu'était « l'ancienne
# forme ».
SCHEMA_03F4646 = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Corporate strategy layer, top of the three-level hierarchy: the "projets corporate" leadership
-- steers by (Native (PT2), VLC (microlink), Nova (PT1)). Under each sit its thÃ©matiques
-- (``thematics``), and under those the Âµprojets (``microprojects``). A Âµprojet belongs to exactly one
-- area; the seeded "non-classe" area holds anything not yet sorted. Visible to every signed-in
-- user (company-wide overview); only an admin (users.is_admin) creates/renames one or moves a
-- Âµprojet between areas.
CREATE TABLE IF NOT EXISTS management_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id),
    objectives_period TEXT NOT NULL DEFAULT '6 prochains mois',
    -- prefix of the numbers its Âµprojets get (Â« Nat Â» -> Nat_0001, Nat_0002...); '' = not numbered
    code_prefix TEXT NOT NULL DEFAULT ''
);

-- Middle level: a technical thÃ©matique of one corporate project (dopage PGaN, double EBL...). It
-- groups the Âµprojets - chains of experiments - that address it. Slug unique within its area only.
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
-- only orders objectives without one (0 = most important). ``achieved`` + the Âµprojet that
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

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- A "Âµprojet" in Spectre's vocabulary: one topic a management area addresses. The table, the
-- on-disk directory (``data/microprojects/<slug>``) and every internal identifier say
-- ``microproject``; only the French user-facing labels and URLs say "Âµprojet" / ``/microprojets``.
CREATE TABLE IF NOT EXISTS microprojects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    management_area_id INTEGER REFERENCES management_areas(id),
    thematic_id INTEGER REFERENCES thematics(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER NOT NULL REFERENCES users(id),
    -- its number, Â« Nat_0004 Â» = prefix + number: given once, when it first lands in a numbered
    -- corporate project, and kept for good (even if it moves) - see spectre.core.microprojects
    code_prefix TEXT,
    code_number INTEGER
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

-- Suivi de lots (spectre.core.lots) : un lot de fabrication = des wafers (par lasermark), une
-- prioritÃ© (P10, P20...), un dÃ©but, une fin prÃ©visionnelle et une fin dÃ©clarÃ©e. DÃ©claratif pour
-- l'instant (source = 'declaratif') ; des datahooks l'alimenteront ensuite. Ses expÃ©riences ne sont
-- pas stockÃ©es ici : ce sont celles qui suivent ses wafers.
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

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_microproject ON invitations(microproject_id);
CREATE INDEX IF NOT EXISTS idx_microproject_links_a ON microproject_links(microproject_a_id);
CREATE INDEX IF NOT EXISTS idx_microproject_links_b ON microproject_links(microproject_b_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_a ON entity_links(a_microproject_slug);
CREATE INDEX IF NOT EXISTS idx_entity_links_b ON entity_links(b_microproject_slug);
CREATE INDEX IF NOT EXISTS idx_thematics_area ON thematics(management_area_id);
CREATE INDEX IF NOT EXISTS idx_area_objectives_area ON area_objectives(management_area_id);
"""

# Ce que l'ancien ``init_db()`` ajoutait au schéma, puis les lignes qu'il semait au premier démarrage.
INIT_DB_03F4646 = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_microprojects_code ON microprojects(code_prefix, code_number) WHERE code_number IS NOT NULL;
INSERT INTO management_areas (slug, name, description) VALUES ('non-classe', 'Non classé', 'µprojets pas encore rattachés à un projet corporate.');
INSERT INTO management_areas (slug, name, code_prefix) VALUES ('native-pt2', 'Native (PT2)', 'Nat');
INSERT INTO management_areas (slug, name, code_prefix) VALUES ('datacom-vlc', 'VLC (microlink)', 'VLC');
INSERT INTO management_areas (slug, name, code_prefix) VALUES ('nova-pt1', 'Nova (PT1)', 'Nov');
INSERT INTO users (id, email, name, password_hash, salt, is_admin) VALUES (1, 'chef@exemple.fr', 'Chef', 'h', 's', 1);
INSERT INTO microprojects (id, slug, name, management_area_id, created_by, code_prefix, code_number)
    VALUES (1, 'recuit-mg', 'Recuit Mg', 2, 1, 'Nat', 1);
INSERT INTO memberships (microproject_id, user_id, role) VALUES (1, 1, 'owner');
INSERT INTO lots (code, priority) VALUES ('LOT-0001', 'P10');
"""


def _plugins():
    from spectre.plugins import PLUGINS

    return PLUGINS


def _schema(path) -> dict:
    """Tables -> colonnes, et noms d'index : ce qui doit coïncider, quel que soit l'ordre des colonnes
    (une colonne ajoutée par ``ALTER TABLE`` arrive en dernier)."""
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        columns = {t: sorted(r[1] for r in conn.execute(f"PRAGMA table_info({t})")) for t in tables}
        indexes = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"))
        return {"columns": columns, "indexes": indexes}
    finally:
        conn.close()


def _dump(path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


def _old_installation(data_dir, rows: str = INIT_DB_03F4646) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.executescript(SCHEMA_03F4646)
    conn.executescript(rows)
    conn.commit()
    conn.close()


def test_a_database_written_by_the_old_code_reaches_the_fresh_schema(data_dir, tmp_path, monkeypatch):
    _old_installation(data_dir)
    run_migrations(_plugins())
    migrated = _schema(data_dir / "spectre.db")

    fresh_dir = tmp_path / "fresh"
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(fresh_dir))
    run_migrations(_plugins())
    assert migrated == _schema(fresh_dir / "spectre.db")

    monkeypatch.setenv("SPECTRE_DATA_DIR", str(data_dir))
    with connect() as conn:
        areas = [r["slug"] for r in conn.execute("SELECT slug FROM management_areas ORDER BY id")]
        code = tuple(conn.execute("SELECT code_prefix, code_number FROM microprojects").fetchone())
        applied = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert areas == ["non-classe", "native-pt2", "datacom-vlc", "nova-pt1"]  # rien de re-semé
    assert code == ("Nat", 1)  # aucun renumérotage
    assert applied == sum(len(plugin.migrations) for plugin in _plugins())


def test_a_second_run_changes_nothing(data_dir):
    _old_installation(data_dir)
    run_migrations(_plugins())
    before = _dump(data_dir / "spectre.db")
    run_migrations(_plugins())
    assert _dump(data_dir / "spectre.db") == before


def test_a_revoked_admin_is_not_promoted_again_on_restart(data_dir):
    from spectre.plugins.accounts import service as accounts

    run_migrations(_plugins())
    accounts.register("premier@exemple.fr", "supersecret", "Premier")
    accounts.set_admin("premier@exemple.fr", False)
    run_migrations(_plugins())
    assert not accounts.get_by_email("premier@exemple.fr").is_admin


def test_an_old_database_without_admin_gets_one_once(data_dir):
    _old_installation(
        data_dir,
        "INSERT INTO users (email, name, password_hash, salt) VALUES ('a@exemple.fr', 'A', 'h', 's'), ('b@exemple.fr', 'B', 'h', 's');",
    )
    from spectre.plugins.accounts import service as accounts

    run_migrations(_plugins())
    assert [accounts.get_by_email(e).is_admin for e in ("a@exemple.fr", "b@exemple.fr")] == [True, False]


def test_a_lot_table_from_the_first_version_gets_its_priority_column(data_dir):
    # The very first lots table (with a route of steps) had no priority: the lots plugin's first
    # migration adds it, the next one drops the steps table nothing reads anymore.
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute(
        "CREATE TABLE lots (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', "
        "description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned', started_on TEXT, forecast_exit_on TEXT, "
        "exited_on TEXT, hold_reason TEXT NOT NULL DEFAULT '', current_step_id INTEGER, source TEXT NOT NULL DEFAULT 'declaratif', "
        "created_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("CREATE TABLE lot_steps (id INTEGER PRIMARY KEY, lot_id INTEGER REFERENCES lots(id), name TEXT)")
    conn.execute("INSERT INTO lots (code) VALUES ('OLD-1')")
    conn.commit()
    conn.close()

    run_migrations(_plugins())
    from spectre.plugins.lots import service as lots

    assert lots.get_by_code("OLD-1").priority == ""
    with connect() as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'lot_steps'").fetchone() is None


# --- l'exécuteur ------------------------------------------------------------------------------


def test_each_migration_runs_once_in_plugin_then_migration_order(data_dir):
    calls = []

    def step(name):
        return lambda conn: calls.append(name)

    first = Plugin("premier", migrations=(Migration("0001", step("premier/0001")), Migration("0002", step("premier/0002"))))
    second = Plugin("second", migrations=(Migration("0001", step("second/0001")),))
    run_migrations([first, second])
    run_migrations([first, second])
    assert calls == ["premier/0001", "premier/0002", "second/0001"]


def test_a_failing_migration_leaves_nothing_behind_and_runs_again(data_dir):
    attempts = []

    def flaky(conn):
        attempts.append(1)
        conn.execute("CREATE TABLE half_done (id INTEGER)")
        if len(attempts) == 1:
            raise RuntimeError("panne")

    plugin = Plugin("demo", migrations=(Migration("0001", "CREATE TABLE kept (id INTEGER);"), Migration("0002", flaky)))
    with pytest.raises(RuntimeError):
        run_migrations([plugin])
    with connect() as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        applied = [r["migration_id"] for r in conn.execute("SELECT migration_id FROM schema_migrations")]
    assert "kept" in tables and "half_done" not in tables
    assert applied == ["0001"]

    run_migrations([plugin])  # le démarrage suivant reprend à la migration qui a échoué
    with connect() as conn:
        applied = [r["migration_id"] for r in conn.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id")]
    assert applied == ["0001", "0002"]


def test_a_script_is_split_on_complete_statements_only(data_dir):
    with connect() as conn:
        execute_script(
            conn,
            """
            -- un commentaire ; avec un point-virgule
            CREATE TABLE notes (id INTEGER, text TEXT DEFAULT 'a;b');
            INSERT INTO notes (id) VALUES (1);
            """,
        )
        assert conn.execute("SELECT text FROM notes").fetchone()["text"] == "a;b"
        with pytest.raises(ValueError):
            execute_script(conn, "CREATE TABLE unfinished (id INTEGER")


def test_rebuild_table_applies_a_non_additive_change_and_keeps_rows_and_indexes(data_dir):
    def create(conn):
        conn.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id), state TEXT, legacy TEXT)")
        conn.execute("CREATE INDEX idx_items_parent ON items(parent_id)")
        conn.execute("INSERT INTO parents (id) VALUES (1)")
        conn.execute("INSERT INTO items (id, parent_id, state, legacy) VALUES (1, 1, 'open', 'x')")

    def tighten(conn):
        rebuild_table(
            conn,
            "items",
            "CREATE TABLE items (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parents(id), "
            "state TEXT NOT NULL CHECK (state IN ('open', 'closed')))",
        )

    run_migrations([Plugin("demo", migrations=(Migration("0001", create), Migration("0002", tighten)))])
    with connect() as conn:
        assert dict(conn.execute("SELECT * FROM items").fetchone()) == {"id": 1, "parent_id": 1, "state": "open"}
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'idx_items_parent'").fetchone() is not None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO items (id, parent_id, state) VALUES (2, 1, 'lost')")


def test_rebuild_table_refuses_to_run_with_foreign_keys_on(data_dir):
    with connect() as conn:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with pytest.raises(RuntimeError):
            rebuild_table(conn, "items", "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
