"""Les droits dans un µprojet (``microprojects.service.access``) : un administrateur et un manager de
l'équipe de son thème ont le rôle owner, même sans en être membres ; les autres ont le rôle de leur
adhésion. L'équipe d'un µprojet est celle de son thème, calculée : un µprojet « Non classé » n'en a
pas."""

from __future__ import annotations

import pytest

from support.accounts import login
from support.http import assert_created, assert_ok
from support.microprojects import add_member, create_microproject, get_microproject, list_microprojects, move_microproject
from support.process_library import create_item, step_preset
from support.teams import set_team_member_role, team_world

# rôle effectif attendu sur « recuit » (thème de l'équipe A), « orphelin » (« Non classé ») et
# « ailleurs » (thème sans équipe), par compte du monde de test : (role, role_source) ou None
EXPECTED = {
    "admin": {"recuit": ("owner", "admin"), "orphelin": ("owner", "admin"), "ailleurs": ("owner", "admin")},
    "manager_a": {"recuit": ("owner", "team_manager"), "orphelin": None, "ailleurs": None},
    "manager_b": {"recuit": None, "orphelin": None, "ailleurs": None},
    "member_a": {"recuit": None, "orphelin": None, "ailleurs": None},
    "researcher": {"recuit": ("owner", "membership"), "orphelin": ("owner", "membership"), "ailleurs": ("owner", "membership")},
    "viewer": {"recuit": ("viewer", "membership"), "orphelin": None, "ailleurs": None},
    "stranger": {"recuit": None, "orphelin": None, "ailleurs": None},
}


@pytest.mark.parametrize("who", sorted(EXPECTED))
def test_the_effective_role_of_each_account(client, who):
    world = team_world(client)
    login(client, getattr(world, who))
    for slug, expected in EXPECTED[who].items():
        response = client.get(f"/api/microprojects/{slug}")
        if expected is None:
            assert response.status_code == 403, (who, slug)
            assert client.get(f"/api/microprojects/{slug}/members").status_code == 403
            continue
        body = assert_ok(response)
        role, _source = expected
        assert (body["role"], body["role_source"]) == expected, (who, slug)
        assert body["can_edit"] is (role in ("editor", "owner"))
        assert body["can_manage"] is (role == "owner")


@pytest.mark.parametrize("who", ["admin", "manager_a"])
def test_the_admin_and_the_team_manager_administer_a_microproject_of_the_team(client, who):
    world = team_world(client)
    login(client, getattr(world, who))
    # membres (owner), réglages (owner), et ce qu'un editor fait (ici : un préréglage du µprojet)
    member = add_member(client, "recuit", world.stranger, "editor")
    assert client.patch(f"/api/microprojects/recuit/members/{member['id']}", json={"role": "viewer"}).status_code == 200
    assert client.delete(f"/api/microprojects/recuit/members/{member['id']}").status_code == 204
    assert assert_ok(client.get("/api/microprojects/recuit/invitations")) == []
    assert client.patch("/api/microprojects/recuit", json={"description": "Revue"}).status_code == 200
    create_item(client, "step-presets", step_preset("Recuit 600"), microproject="recuit")
    assert client.delete("/api/microprojects/recuit", params={"confirm_name": "Recuit"}).status_code == 204


@pytest.mark.parametrize("who", ["manager_b", "member_a", "viewer", "stranger"])
def test_the_others_do_not_administer_it(client, who):
    world = team_world(client)
    login(client, getattr(world, who))
    assert client.post("/api/microprojects/recuit/members", json={"email": world.stranger, "role": "viewer"}).status_code == 403
    assert client.patch("/api/microprojects/recuit", json={"description": "x"}).status_code == 403
    assert client.get("/api/microprojects/recuit/invitations").status_code == 403
    refused = client.post("/api/step-presets", json={**step_preset("P"), "scope": "microproject", "microproject": "recuit"})
    assert refused.status_code == 403
    assert client.delete("/api/microprojects/recuit", params={"confirm_name": "Recuit"}).status_code == 403


def test_my_microprojects_include_those_of_the_teams_i_manage(client):
    world = team_world(client)
    login(client, world.manager_a)
    mine = {p["slug"]: (p["role"], p["role_source"]) for p in list_microprojects(client)}
    assert mine == {"recuit": ("owner", "team_manager")}
    login(client, world.manager_b)
    assert list_microprojects(client) == []
    login(client, world.admin)  # l'admin voit tout, mais « ses » µprojets restent les siens
    assert list_microprojects(client) == []
    every = {p["slug"]: p["role_source"] for p in list_microprojects(client, scope="all")}
    assert every == {"recuit": "admin", "orphelin": "admin", "ailleurs": "admin"}
    login(client, world.researcher)
    assert {p["slug"] for p in list_microprojects(client)} == {"recuit", "orphelin", "ailleurs"}


def test_a_microproject_follows_the_team_of_its_area(client):
    """L'équipe d'un µprojet n'est jamais stockée : déplacé dans un autre thème, il en prend l'équipe."""
    world = team_world(client)
    login(client, world.researcher)
    move_microproject(client, "native-pt2", "recuit")
    login(client, world.manager_a)
    assert client.get("/api/microprojects/recuit").status_code == 403
    assert list_microprojects(client) == []

    login(client, world.researcher)
    move_microproject(client, "theme-a", "orphelin")  # un µprojet « Non classé » rejoint un thème d'équipe
    login(client, world.manager_a)
    assert get_microproject(client, "orphelin")["role_source"] == "team_manager"

    # rétrogradé simple membre, le manager perd ses droits sur le µprojet
    login(client, world.admin)
    assert set_team_member_role(client, "equipe-a", world.ids[world.member_a], "manager").status_code == 200  # l'équipe garde un manager
    assert set_team_member_role(client, "equipe-a", world.ids[world.manager_a], "member").status_code == 200
    login(client, world.manager_a)
    assert client.get("/api/microprojects/orphelin").status_code == 403


def test_a_member_owner_stays_one_and_a_manager_member_is_shown_as_member_owner(client):
    world = team_world(client)
    login(client, world.researcher)
    add_member(client, "recuit", world.manager_a, "viewer")
    login(client, world.manager_a)
    body = get_microproject(client, "recuit")
    # viewer par adhésion, mais owner comme manager de l'équipe : le rôle le plus fort l'emporte
    assert (body["role"], body["role_source"]) == ("owner", "team_manager")
    login(client, world.researcher)
    assert client.patch(f"/api/microprojects/recuit/members/{world.ids[world.manager_a]}", json={"role": "owner"}).status_code == 200
    login(client, world.manager_a)
    assert (get_microproject(client, "recuit")["role"], get_microproject(client, "recuit")["role_source"]) == ("owner", "membership")


def test_the_role_reaches_the_lists_of_other_plugins(client):
    """Les autres plugins lisent la même règle : statistiques, liens, plaques."""
    world = team_world(client)
    login(client, world.manager_a)
    stats = {row["microproject"]["slug"]: (row["microproject"]["role"], row["microproject"]["role_source"]) for row in assert_ok(client.get("/api/experiment-stats"))}
    assert stats["recuit"] == ("owner", "team_manager") and stats["orphelin"] == (None, None)
    assert client.get("/api/wafers", params={"microproject": "recuit"}).status_code == 200
    assert client.get("/api/wafers", params={"microproject": "orphelin"}).status_code == 403
    assert client.get("/api/microproject-links", params={"microproject": "recuit"}).status_code == 200

    login(client, world.researcher)
    create_microproject(client, "Recuit bis", area="theme-a")
    login(client, world.manager_a)
    link = client.post("/api/microproject-links", json={"a": "recuit", "b": "recuit-bis", "note": "même four"})
    assert_created(link)
    assert client.post("/api/microproject-links", json={"a": "recuit", "b": "orphelin", "note": ""}).status_code == 403
