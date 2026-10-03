"""Les migrations du plugin microprojects sur une base existante."""

from __future__ import annotations

import dataclasses

from spectre.kernel.db import column_names, connect, run_migrations
from spectre.plugins import PLUGINS


def test_an_invitation_sent_before_the_migration_still_opens(data_dir):
    """Une invitation d'avant gardait son jeton en clair : la migration lui donne un id et hache le
    jeton en place, si bien que le lien déjà envoyé fonctionne toujours."""
    from spectre.plugins.microprojects import service as microprojects

    before = tuple(
        dataclasses.replace(plugin, migrations=plugin.migrations[:-1]) if plugin.name == "microprojects" else plugin for plugin in PLUGINS
    )
    run_migrations(before)
    conn = connect()
    conn.execute("INSERT INTO users (id, email, name, password_hash, salt) VALUES (1, 'chef@exemple.fr', 'Chef', 'h', 's')")
    conn.execute("INSERT INTO microprojects (id, slug, name, created_by) VALUES (1, 'recuit', 'Recuit', 1)")
    conn.execute(
        "INSERT INTO invitations (token, microproject_id, email, role, invited_by, expires_at) "
        "VALUES ('jeton-en-clair', 1, 'bob@exemple.fr', 'editor', 1, datetime('now', '+1 day'))"
    )
    conn.commit()
    conn.close()

    run_migrations(PLUGINS)

    invitation = microprojects.get_invitation("jeton-en-clair")
    assert (invitation.id, invitation.email, invitation.role) == (1, "bob@exemple.fr", "editor")
    conn = connect()
    columns = column_names(conn, "invitations")
    stored = conn.execute("SELECT token_hash FROM invitations").fetchone()["token_hash"]
    conn.close()
    assert "token" not in columns and {"id", "token_hash"} <= columns
    assert stored != "jeton-en-clair" and len(stored) == 64
