"""SQLite storage for everything Follow and StructureForge don't model. Deliberately the only
relational piece of Spectre - both dependencies (plus Spectre's own libraries, e.g. the step preset
store) keep their own data as flat JSON files (see ``follow.storage.backends.JsonFileStore``), and
Spectre does not touch that; the database only ever stores rows that need to be queried by
something other than an id (an email, a microproject membership).

The kernel owns the connection and the migration runner, never a table: each plugin declares its
own schema as versioned :class:`~spectre.kernel.plugin.Migration` steps (its ``migrations.py``),
applied once each, in the order of the plugins then of their migrations - see
:func:`run_migrations`.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from .plugin import Plugin

logger = logging.getLogger(__name__)

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    plugin TEXT NOT NULL,
    migration_id TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (plugin, migration_id)
)
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


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


def _only_comments(sql: str) -> bool:
    return all(not line.strip() or line.strip().startswith("--") for line in sql.splitlines())


def execute_script(conn: sqlite3.Connection, script: str) -> None:
    """Run ``script`` statement by statement, inside the current transaction - unlike
    ``executescript()``, which commits whatever is pending first. A statement ends at the end of
    the line that completes it (``sqlite3.complete_statement``), so a ``;`` in a comment or a
    string never splits one.
    """
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            conn.execute(pending)
            pending = ""
    if not _only_comments(pending):
        raise ValueError(f"instruction SQL incomplète en fin de script : {pending.strip()[:80]!r}")


def backups_dir() -> Path:
    """Where :func:`run_migrations` saves the data before migrating it: one ``<timestamp>``
    directory per start-up that had migrations to apply."""
    return data_dir() / "backups"


def _backup_database(conn: sqlite3.Connection) -> Path:
    """Copy the database into a new directory of :func:`backups_dir` (sqlite3's backup API: a
    consistent copy of a file still open) - returns that directory."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups_dir() / stamp
    suffix = 2
    while target.exists():
        target = backups_dir() / f"{stamp}-{suffix}"
        suffix += 1
    target.mkdir(parents=True)
    copy = sqlite3.connect(target / "spectre.db")
    try:
        conn.backup(copy)
    finally:
        copy.close()
    return target


def _backup_files(target: Path, files: Iterable[Path]) -> None:
    """Copy ``files`` into ``target``, at their path relative to ``data_dir()`` - a file already
    saved there is kept (its state before the first migration that touched it)."""
    root = data_dir()
    for path in files:
        path = Path(path).resolve()
        if not path.is_file() or not path.is_relative_to(root) or path.is_relative_to(backups_dir()):
            continue
        destination = target / path.relative_to(root)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def run_migrations(plugins: Iterable[Plugin]) -> None:
    """Apply every migration not yet recorded in ``schema_migrations``, in the order of
    ``plugins`` then of each plugin's ``migrations`` - one transaction per migration, recorded in
    the same transaction, so an interrupted start-up resumes at the migration that failed.

    Before the first pending migration of an existing installation (a database with tables, or
    files a pending migration declares), the database is saved under :func:`backups_dir`, and the
    files each migration declares (``Migration.files``) right before it runs - a migration may
    drop or rewrite data the previous code still reads, and that code can't read migrated data.

    Foreign keys are off for the whole run (SQLite ignores ``PRAGMA foreign_keys`` inside a
    transaction, and :func:`rebuild_table` needs them off); a rebuilt table is checked with
    ``foreign_key_check`` before its migration commits.
    """
    conn = connect()
    conn.isolation_level = None  # transactions explicites : BEGIN / COMMIT ci-dessous
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        existing = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name != 'schema_migrations'").fetchone()
        conn.execute(_MIGRATIONS_TABLE)
        applied = {(row["plugin"], row["migration_id"]) for row in conn.execute("SELECT plugin, migration_id FROM schema_migrations")}
        pending = [(plugin, migration) for plugin in plugins for migration in plugin.migrations if (plugin.name, migration.id) not in applied]
        backup = None
        if pending and (existing or any(Path(path).is_file() for _p, m in pending if m.files for path in m.files())):
            backup = _backup_database(conn)
            logger.warning("%d migration(s) en attente : données sauvegardées dans %s", len(pending), backup)
        for plugin, migration in pending:
            if backup is not None and migration.files:
                # juste avant la migration : une migration précédente a pu déplacer ces fichiers
                _backup_files(backup, migration.files())
            conn.execute("BEGIN")
            try:
                if isinstance(migration.apply, str):
                    execute_script(conn, migration.apply)
                else:
                    migration.apply(conn)
                conn.execute("INSERT INTO schema_migrations (plugin, migration_id) VALUES (?, ?)", (plugin.name, migration.id))
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


_CREATE_TABLE_RE = r"^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)[\"`\[]?{table}[\"`\]]?(?=\s*\()"


def rebuild_table(conn: sqlite3.Connection, table: str, new_ddl: str) -> None:
    """Recreate ``table`` from ``new_ddl`` (its full ``CREATE TABLE``) - the change ``ALTER TABLE``
    can't make (a ``CHECK``, a ``NOT NULL``, a column dropped). The order SQLite documents: create
    the new table under a temporary name, copy the columns both versions share, drop the old one,
    rename the new one, recreate the old one's indexes, then ``foreign_key_check``.

    For a migration only: :func:`run_migrations` has foreign keys off, which this requires -
    dropping a parent table with them on would cascade, or fail.
    """
    if conn.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise RuntimeError("rebuild_table() exige des clés étrangères désactivées (appelez-la depuis une migration)")
    temporary = f"_rebuild_{table}"
    ddl, count = re.subn(_CREATE_TABLE_RE.format(table=re.escape(table)), rf"\g<1>{temporary}", new_ddl, count=1, flags=re.IGNORECASE)
    if not count:
        raise ValueError(f"le DDL fourni ne crée pas la table {table!r}")
    indexes = [
        row["sql"]
        for row in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,))
    ]
    old_columns = column_names(conn, table)
    conn.execute(ddl)
    shared = ", ".join(name for name in _ordered_columns(conn, temporary) if name in old_columns)
    conn.execute(f"INSERT INTO {temporary} ({shared}) SELECT {shared} FROM {table}")
    sequence = _sequence(conn, table)
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
    if sequence is not None and table_exists(conn, "sqlite_sequence"):
        # le compteur d'AUTOINCREMENT disparaît avec l'ancienne table : sans lui, la nouvelle repartirait
        # du plus grand id restant et redonnerait l'id d'une ligne supprimée (l'id d'un lot est son URL)
        conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?", (sequence, table))
        if not conn.execute("SELECT 1 FROM sqlite_sequence WHERE name = ?", (table,)).fetchone() and _autoincrement(conn, table):
            conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, sequence))
    for sql in indexes:
        conn.execute(sql)
    violations = conn.execute(f"PRAGMA foreign_key_check({table})").fetchall()
    if violations:
        raise sqlite3.IntegrityError(f"{len(violations)} ligne(s) de {table!r} violent une clé étrangère après reconstruction")


def _sequence(conn: sqlite3.Connection, table: str) -> int | None:
    """Le compteur d'AUTOINCREMENT de ``table`` (``None`` sans compteur)."""
    if not table_exists(conn, "sqlite_sequence"):
        return None
    row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)).fetchone()
    return row[0] if row else None


def _autoincrement(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return bool(row and re.search(r"\bAUTOINCREMENT\b", row[0], re.IGNORECASE))


def _ordered_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
