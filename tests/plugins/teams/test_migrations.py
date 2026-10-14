"""Les installations d'avant les équipes, puis d'avant plusieurs équipes par projet.

1. Une installation sans équipes : la migration crée les tables des équipes et celles des projets, sans rien
   rattacher, si bien que les droits restent ceux d'avant (l'administrateur seul écrit les projets ; dans un
   µprojet, le rôle de son adhésion).
2. Une installation où un projet n'avait qu'une équipe (``management_areas.team_id``) : cette équipe devient
   la première de ``area_teams``, elle possède les thématiques et les µprojets du projet, et la colonne
   disparaît.
"""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from spectre.kernel.db import column_names, connect, run_migrations
from spectre.plugins import PLUGINS
from support.accounts import login
from support.http import assert_ok


def _before_teams():
    """Les plugins tels qu'avant ce chantier : sans teams, et areas sans sa migration 0003_team."""
    truncated = {"areas": 2, "microprojects": 4}
    return tuple(
        dataclasses.replace(plugin, depends_on=("accounts",) if plugin.name == "areas" else plugin.depends_on, migrations=plugin.migrations[: truncated[plugin.name]])
        if plugin.name in truncated
        else plugin
        for plugin in PLUGINS
        if plugin.name != "teams"
    )


def _one_team_per_area():
    """Les plugins tels qu'avant plusieurs équipes par projet : areas jusqu'à 0003_team (``team_id``),
    microprojects jusqu'à 0004, teams sans son badge."""
    truncated = {"areas": 3, "microprojects": 4, "teams": 1}
    return tuple(
        dataclasses.replace(plugin, migrations=plugin.migrations[: truncated[plugin.name]]) if plugin.name in truncated else plugin
        for plugin in PLUGINS
    )


def test_an_existing_installation_keeps_its_rights(data_dir):
    from spectre.plugins.accounts import service as accounts

    run_migrations(_before_teams())
    accounts.register("boss@example.com", "supersecret", "Boss")  # le premier compte : admin
    chef = accounts.register("chef@example.com", "supersecret", "Chef")
    accounts.register("lecteur@example.com", "supersecret", "Lecteur")
    conn = connect()  # le µprojet s'écrit en SQL : le code courant lit des tables d'équipes que cette base n'a pas encore
    area_id = conn.execute("SELECT id FROM management_areas WHERE slug = 'native-pt2'").fetchone()["id"]
    conn.execute(
        "INSERT INTO microprojects (id, slug, name, created_by, management_area_id) VALUES (1, 'recuit', 'Recuit', ?, ?)",
        (chef.id, area_id),
    )
    conn.execute("INSERT INTO memberships (microproject_id, user_id, role) VALUES (1, ?, 'owner')", (chef.id,))
    conn.execute("INSERT INTO memberships (microproject_id, user_id, role) VALUES (1, 3, 'viewer')")
    conn.commit()
    assert "team_id" not in column_names(conn, "management_areas")
    conn.close()

    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:  # applique les migrations en attente
        conn = connect()
        assert {"teams", "team_members", "area_teams", "thematic_teams"} <= {
            row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert conn.execute("SELECT COUNT(*) FROM area_teams").fetchone()[0] == 0
        applied = {(row["plugin"], row["migration_id"]) for row in conn.execute("SELECT plugin, migration_id FROM schema_migrations")}
        conn.close()
        assert {("teams", "0001_initial"), ("areas", "0003_team"), ("areas", "0004_teams_per_area"), ("microprojects", "0005_team")} <= applied

        login(client, "chef@example.com")
        assert assert_ok(client.get("/api/teams")) == []
        area = assert_ok(client.get("/api/areas/native-pt2"))
        assert (area["teams"], area["can_manage"]) == ([], False)
        assert client.patch("/api/areas/native-pt2", json={"description": "x"}).status_code == 403
        assert client.post("/api/areas", json={"name": "Nouveau"}).status_code == 403
        mine = assert_ok(client.get("/api/microprojects"))
        assert [(p["slug"], p["role"], p["role_source"], p["team"]) for p in mine] == [("recuit", "owner", "membership", None)]

        login(client, "lecteur@example.com")
        body = assert_ok(client.get("/api/microprojects/recuit"))
        assert (body["role"], body["role_source"], body["can_edit"]) == ("viewer", "membership", False)
        assert client.patch("/api/microprojects/recuit", json={"name": "x"}).status_code == 403

        login(client, "boss@example.com")
        assert client.patch("/api/areas/native-pt2", json={"description": "x"}).status_code == 200


def test_an_area_with_one_team_gives_it_its_thematics_and_microprojects(data_dir):
    run_migrations(_one_team_per_area())
    conn = connect()
    conn.execute("INSERT INTO users (id, email, name, password_hash, salt) VALUES (1, 'chef@exemple.fr', 'Chef', 'h', 's')")
    conn.execute("INSERT INTO teams (id, slug, name) VALUES (1, 'epi', 'Épi')")
    conn.execute("INSERT INTO team_members (team_id, user_id, role) VALUES (1, 1, 'manager')")
    conn.execute("UPDATE management_areas SET team_id = 1 WHERE slug = 'native-pt2'")  # l'ancien modèle : une équipe par projet
    area = conn.execute("SELECT id FROM management_areas WHERE slug = 'native-pt2'").fetchone()["id"]
    other = conn.execute("SELECT id FROM management_areas WHERE slug = 'nova-pt1'").fetchone()["id"]
    conn.execute("INSERT INTO thematics (id, management_area_id, slug, name) VALUES (1, ?, 'dopage', 'Dopage')", (area,))
    conn.execute("INSERT INTO thematics (id, management_area_id, slug, name) VALUES (2, ?, 'libre', 'Libre')", (other,))
    for slug, area_id, thematic_id in (("recuit", area, 1), ("gravure", area, None), ("ailleurs", other, 2)):
        conn.execute(
            "INSERT INTO microprojects (slug, name, created_by, management_area_id, thematic_id) VALUES (?, ?, 1, ?, ?)",
            (slug, slug, area_id, thematic_id),
        )
    conn.commit()
    conn.close()

    run_migrations(PLUGINS)

    conn = connect()
    assert "team_id" not in column_names(conn, "management_areas")
    assert [(row["management_area_id"], row["team_id"]) for row in conn.execute("SELECT * FROM area_teams")] == [(area, 1)]
    thematics = {row["slug"]: row["team_id"] for row in conn.execute("SELECT slug, team_id FROM thematics")}
    assert thematics == {"dopage": 1, "libre": None}  # un projet sans équipe : des thématiques ouvertes
    microprojects = {row["slug"]: row["team_id"] for row in conn.execute("SELECT slug, team_id FROM microprojects")}
    assert microprojects == {"recuit": 1, "gravure": 1, "ailleurs": None}
    teams = {row["slug"]: (row["color"], row["badge"]) for row in conn.execute("SELECT slug, color, badge FROM teams")}
    assert teams == {"epi": ("#1f6feb", "")}
    conn.close()
