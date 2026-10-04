"""Les équipes et leurs membres : un administrateur crée, renomme et supprime une équipe ; un
administrateur ou un manager de l'équipe en gère les membres ; une équipe garde un manager."""

from __future__ import annotations

from support.accounts import login, signup
from support.areas import create_area, get_area, set_area_team
from support.http import assert_created, assert_handler_404, assert_ok
from support.teams import (
    add_team_member,
    create_team,
    get_team,
    list_teams,
    remove_team_member,
    set_team_member_role,
    team_members,
)


def _accounts(client) -> dict[str, int]:
    """boss (admin, premier compte), chef, equipier, inconnu - le client reste sur boss."""
    ids = {name: signup(client, f"{name}@example.com", name=name.capitalize())["id"] for name in ("boss", "chef", "equipier", "inconnu")}
    login(client, "boss@example.com")
    return ids


def test_an_admin_creates_renames_and_deletes_a_team(client):
    _accounts(client)
    created = client.post("/api/teams", json={"name": "Épitaxie"})
    assert created.status_code == 201
    assert created.headers["location"] == "/api/teams/epitaxie"
    team = created.json()
    assert (team["slug"], team["name"], team["member_count"], team["managers"]) == ("epitaxie", "Épitaxie", 0, [])
    assert (team["my_role"], team["can_edit"], team["can_manage"]) == (None, True, True)
    assert create_team(client, "Épitaxie")["slug"] == "epitaxie-2"  # un nom pris : un slug suffixé

    renamed = client.patch("/api/teams/epitaxie", json={"name": "Épitaxie MOCVD"})
    assert renamed.status_code == 200 and (renamed.json()["slug"], renamed.json()["name"]) == ("epitaxie", "Épitaxie MOCVD")
    assert client.patch("/api/teams/epitaxie", json={"name": "  "}).status_code == 422

    deleted = client.delete("/api/teams/epitaxie")
    assert deleted.status_code == 204 and deleted.content == b""
    assert_handler_404(client.get("/api/teams/epitaxie"), "epitaxie")
    assert [t["slug"] for t in list_teams(client)] == ["epitaxie-2"]


def test_only_an_admin_creates_renames_or_deletes_a_team(client):
    ids = _accounts(client)
    create_team(client, "Épitaxie")
    assert_created(add_team_member(client, "epitaxie", "chef@example.com", "manager"))

    login(client, "chef@example.com")
    assert client.post("/api/teams", json={"name": "Autre"}).status_code == 403
    assert client.patch("/api/teams/epitaxie", json={"name": "x"}).status_code == 403
    assert client.delete("/api/teams/epitaxie").status_code == 403
    team = get_team(client, "epitaxie")
    assert (team["my_role"], team["can_edit"], team["can_manage"]) == ("manager", False, True)
    assert team["managers"] == [{"id": ids["chef"], "name": "Chef"}]


def test_every_signed_in_user_reads_the_teams_and_their_members(client):
    ids = _accounts(client)
    create_team(client, "Épitaxie")
    assert_created(add_team_member(client, "epitaxie", "equipier@example.com", "member"))
    assert_created(add_team_member(client, "epitaxie", "chef@example.com", "manager"))

    login(client, "inconnu@example.com")
    [team] = list_teams(client)
    assert (team["member_count"], team["my_role"], team["can_edit"], team["can_manage"]) == (2, None, False, False)
    assert [(m["id"], m["role"]) for m in team_members(client, "epitaxie")] == [(ids["chef"], "manager"), (ids["equipier"], "member")]
    member = assert_ok(client.get(f"/api/teams/epitaxie/members/{ids['equipier']}"))
    assert member == {"id": ids["equipier"], "name": "Equipier", "email": "equipier@example.com", "role": "member"}
    assert_handler_404(client.get(f"/api/teams/epitaxie/members/{ids['inconnu']}"))
    assert_handler_404(client.get("/api/teams/inconnue"))
    assert_handler_404(client.get("/api/teams/inconnue/members"))


def test_an_admin_or_a_manager_of_the_team_manages_its_members(client):
    ids = _accounts(client)
    create_team(client, "Épitaxie")
    added = add_team_member(client, "epitaxie", "chef@example.com", "manager")
    assert added.status_code == 201
    assert added.headers["location"] == f"/api/teams/epitaxie/members/{ids['chef']}"
    assert added.json()["role"] == "manager"

    login(client, "chef@example.com")  # un manager de l'équipe
    assert_created(add_team_member(client, "epitaxie", "equipier@example.com"))
    assert set_team_member_role(client, "epitaxie", ids["equipier"], "manager").json()["role"] == "manager"
    assert set_team_member_role(client, "epitaxie", ids["equipier"], "member").status_code == 200

    login(client, "equipier@example.com")  # un simple membre
    assert add_team_member(client, "epitaxie", "inconnu@example.com").status_code == 403
    assert set_team_member_role(client, "epitaxie", ids["equipier"], "manager").status_code == 403
    assert remove_team_member(client, "epitaxie", ids["chef"]).status_code == 403

    login(client, "inconnu@example.com")  # hors de l'équipe
    assert add_team_member(client, "epitaxie", "inconnu@example.com").status_code == 403

    login(client, "chef@example.com")
    removed = remove_team_member(client, "epitaxie", ids["equipier"])
    assert removed.status_code == 204 and removed.content == b""
    assert [m["id"] for m in team_members(client, "epitaxie")] == [ids["chef"]]


def test_adding_a_member_checks_the_account_the_role_and_duplicates(client):
    _accounts(client)
    create_team(client, "Épitaxie")
    assert_created(add_team_member(client, "epitaxie", "Chef@Example.com "))  # l'adresse telle que tapée
    duplicate = add_team_member(client, "epitaxie", "chef@example.com", "manager")
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "already_member"
    unknown = add_team_member(client, "epitaxie", "personne@example.com")
    assert unknown.status_code == 404 and unknown.json()["code"] == "no_account"
    assert add_team_member(client, "epitaxie", "equipier@example.com", "owner").status_code == 422
    assert_handler_404(add_team_member(client, "inconnue", "equipier@example.com"))


def test_a_team_keeps_at_least_one_manager(client):
    ids = _accounts(client)
    create_team(client, "Épitaxie")
    assert_created(add_team_member(client, "epitaxie", "chef@example.com", "manager"))
    assert_created(add_team_member(client, "epitaxie", "equipier@example.com", "member"))

    for response in (
        set_team_member_role(client, "epitaxie", ids["chef"], "member"),
        remove_team_member(client, "epitaxie", ids["chef"]),
    ):
        assert response.status_code == 409 and response.json()["code"] == "last_manager"
    assert set_team_member_role(client, "epitaxie", ids["chef"], "manager").status_code == 200  # sans effet : accepté

    # avec un second manager, le premier peut partir - y compris de lui-même
    assert set_team_member_role(client, "epitaxie", ids["equipier"], "manager").status_code == 200
    login(client, "chef@example.com")
    assert remove_team_member(client, "epitaxie", ids["chef"]).status_code == 204
    assert add_team_member(client, "epitaxie", "inconnu@example.com").status_code == 403  # il n'en est plus manager
    login(client, "boss@example.com")
    assert_handler_404(set_team_member_role(client, "epitaxie", ids["chef"], "member"))  # plus membre
    assert_handler_404(remove_team_member(client, "epitaxie", ids["chef"]))


def test_deleting_a_team_detaches_its_projects(client):
    _accounts(client)
    create_team(client, "Épitaxie")
    assert_created(add_team_member(client, "epitaxie", "chef@example.com", "manager"))
    create_area(client, "Thème A")
    assert set_area_team(client, "theme-a", "epitaxie")["team"] == {"slug": "epitaxie", "name": "Épitaxie"}
    assert [a["slug"] for a in assert_ok(client.get("/api/areas", params={"team": "epitaxie"}))] == ["theme-a"]

    assert client.delete("/api/teams/epitaxie").status_code == 204
    area = get_area(client, "theme-a")
    assert area["team"] is None
    login(client, "chef@example.com")
    assert get_area(client, "theme-a")["can_manage"] is False
    assert client.patch("/api/areas/theme-a", json={"name": "x"}).status_code == 403
    assert_handler_404(client.get("/api/areas", params={"team": "epitaxie"}))
