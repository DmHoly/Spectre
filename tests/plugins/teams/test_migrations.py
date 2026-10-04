"""Une installation d'avant les équipes : la migration crée les tables des équipes et la colonne
``management_areas.team_id`` sans rien rattacher, si bien que les droits restent ceux d'avant
(l'administrateur seul écrit les projets ; dans un µprojet, le rôle de son adhésion)."""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from spectre.kernel.db import column_names, connect, run_migrations
from spectre.plugins import PLUGINS
from support.accounts import login
from support.http import assert_ok


def _before_teams():
    """Les plugins tels qu'avant ce chantier : sans teams, et areas sans sa migration 0003_team."""
    return tuple(
        dataclasses.replace(plugin, depends_on=("accounts",), migrations=plugin.migrations[:2]) if plugin.name == "areas" else plugin
        for plugin in PLUGINS
        if plugin.name != "teams"
    )


def test_an_existing_installation_keeps_its_rights(data_dir):
    from spectre.plugins.accounts import service as accounts
    from spectre.plugins.microprojects import service as microprojects

    run_migrations(_before_teams())
    accounts.register("boss@example.com", "supersecret", "Boss")  # le premier compte : admin
    chef = accounts.register("chef@example.com", "supersecret", "Chef")
    accounts.register("lecteur@example.com", "supersecret", "Lecteur")
    recuit = microprojects.create("Recuit", "", owner=chef, area="native-pt2")
    conn = connect()
    conn.execute("INSERT INTO memberships (microproject_id, user_id, role) VALUES (?, 3, 'viewer')", (recuit.id,))
    conn.commit()
    assert "team_id" not in column_names(conn, "management_areas")
    conn.close()

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:  # applique les migrations en attente
        conn = connect()
        assert {"teams", "team_members"} <= {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert conn.execute("SELECT COUNT(*) FROM management_areas WHERE team_id IS NOT NULL").fetchone()[0] == 0
        applied = {(row["plugin"], row["migration_id"]) for row in conn.execute("SELECT plugin, migration_id FROM schema_migrations")}
        conn.close()
        assert {("teams", "0001_initial"), ("areas", "0003_team")} <= applied

        login(client, "chef@example.com")
        assert assert_ok(client.get("/api/teams")) == []
        area = assert_ok(client.get("/api/areas/native-pt2"))
        assert (area["team"], area["can_manage"]) == (None, False)
        assert client.patch("/api/areas/native-pt2", json={"description": "x"}).status_code == 403
        assert client.post("/api/areas", json={"name": "Nouveau"}).status_code == 403
        mine = assert_ok(client.get("/api/microprojects"))
        assert [(p["slug"], p["role"], p["role_source"]) for p in mine] == [("recuit", "owner", "membership")]

        login(client, "lecteur@example.com")
        body = assert_ok(client.get("/api/microprojects/recuit"))
        assert (body["role"], body["role_source"], body["can_edit"]) == ("viewer", "membership", False)
        assert client.patch("/api/microprojects/recuit", json={"name": "x"}).status_code == 403

        login(client, "boss@example.com")
        assert client.patch("/api/areas/native-pt2", json={"description": "x"}).status_code == 200
