from __future__ import annotations

import sqlite3

import pytest

from spectre.kernel.db import connect, run_migrations


def test_an_existing_lots_table_gets_its_source_check_and_iso_versions(data_dir):
    # Un lot écrit avant la migration 0003 : source libre, updated_at « AAAA-MM-JJ HH:MM:SS ».
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute(
        "CREATE TABLE lots (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', "
        "description TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned', "
        "started_on TEXT, forecast_exit_on TEXT, exited_on TEXT, hold_reason TEXT NOT NULL DEFAULT '', "
        "source TEXT NOT NULL DEFAULT 'declaratif', created_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), "
        "updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO lots (code, source, updated_at) VALUES ('OLD-1', 'manuel', '2026-01-02 03:04:05')")
    conn.execute("INSERT INTO lots (code, source) VALUES ('OLD-2', 'prism')")
    conn.commit()
    conn.close()

    from spectre.plugins import PLUGINS
    from spectre.plugins.lots import service as lots

    run_migrations(PLUGINS)
    old, prism = lots.list_lots(code="OLD-1")[0], lots.list_lots(code="OLD-2")[0]
    assert (old.source, old.updated_at) == ("declaratif", "2026-01-02T03:04:05+00:00")
    assert prism.source == "prism" and " " not in prism.updated_at
    with connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE lots SET source = 'excel'")
