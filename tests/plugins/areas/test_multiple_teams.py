"""Plusieurs équipes dans un même projet corporate : chacune possède ses thématiques et ses µprojets, que
les autres ne voient pas sans invitation - l'équipe entière invitée dans une thématique la lit (lecture
seule), et quiconque est ajouté à un µprojet voit sa thématique et lit les autres µprojets de celle-ci."""

from __future__ import annotations

from typing import NamedTuple

from support.accounts import login, signup
from support.areas import attach_team, create_area, create_thematic, get_area, invite_team
from support.experiments import launch
from support.http import assert_created, assert_ok
from support.microprojects import add_member, create_microproject, get_microproject, list_microprojects
from support.teams import add_team_member, create_team


class World(NamedTuple):
    admin: str
    manager_a: str
    manager_b: str
    member_b: str
    outsider: str  # dans aucune équipe
    both: str  # manager des deux équipes


def _world(client) -> World:
    """Les équipes A et B travaillent dans « Projet » ; A y possède la thématique « ta » et son µprojet
    « mp-a », B la thématique « tb » et son µprojet « mp-b »."""
    emails = ("boss@example.com", "chef-a@example.com", "chef-b@example.com", "equipier-b@example.com", "dehors@example.com", "double@example.com")
    for email in emails:
        signup(client, email, name=email.split("@")[0])
    admin, manager_a, manager_b, member_b, outsider, both = emails
    login(client, admin)
    create_team(client, "Équipe A")
    create_team(client, "Équipe B")
    for team, email, role in (("equipe-a", manager_a, "manager"), ("equipe-b", manager_b, "manager"), ("equipe-b", member_b, "member"),
                              ("equipe-a", both, "manager"), ("equipe-b", both, "manager")):
        assert_created(add_team_member(client, team, email, role))
    create_area(client, "Projet")
    attach_team(client, "projet", "equipe-a")
    attach_team(client, "projet", "equipe-b")

    login(client, manager_a)
    assert create_thematic(client, "projet", "TA")["team"]["slug"] == "equipe-a"  # la seule équipe qu'il manage ici
    create_microproject(client, "MP A", area="projet", thematic="ta")
    login(client, manager_b)
    assert create_thematic(client, "projet", "TB")["team"]["slug"] == "equipe-b"
    create_microproject(client, "MP B", area="projet", thematic="tb")
    login(client, admin)
    return World(*emails)


def _thematics(client, area="projet") -> list[str]:
    return [t["slug"] for t in get_area(client, area)["thematics"]]


def test_each_team_only_sees_its_own_thematics_and_its_projects_are_open_to_all(client):
    world = _world(client)
    assert [t["slug"] for t in get_area(client, "projet")["teams"]] == ["equipe-a", "equipe-b"]
    badge = get_area(client, "projet")["teams"][0]
    assert (badge["name"], badge["short"]) == ("Équipe A", "ÉA") and badge["color"].startswith("#")

    expected = {world.admin: ["ta", "tb"], world.manager_a: ["ta"], world.manager_b: ["tb"], world.member_b: ["tb"], world.outsider: [], world.both: ["ta", "tb"]}
    for email, thematics in expected.items():
        login(client, email)
        assert _thematics(client) == thematics, email
        assert [a["slug"] for a in assert_ok(client.get("/api/areas")) if a["slug"] == "projet"] == ["projet"]  # le projet reste visible
        assert [t["slug"] for t in assert_ok(client.get("/api/thematics"))] == thematics


def test_another_teams_thematic_and_microprojects_do_not_exist_for_you(client):
    world = _world(client)
    login(client, world.manager_b)
    assert client.get("/api/areas/projet/thematics/ta").status_code == 404
    assert client.patch("/api/areas/projet/thematics/ta", json={"description": "x"}).status_code == 404
    assert client.post("/api/areas/projet/thematics/ta/teams", json={"team": "equipe-b"}).status_code == 404
    assert client.get("/api/microprojects/mp-a").status_code == 403
    stats = {row["microproject"]["slug"] for row in assert_ok(client.get("/api/experiment-stats"))}
    assert "mp-a" not in stats and "mp-b" in stats
    assert assert_ok(client.get("/api/experiment-timeline", params={"area": "projet"})) is not None
    assert client.get("/api/experiment-timeline", params={"area": "projet", "thematic": "ta"}).status_code == 404
    assert list_microprojects(client, q="MP A") == [] and [p["slug"] for p in list_microprojects(client, q="MP")] == ["mp-b"]
    # elle ne place rien dans la thématique de l'autre équipe
    assert client.post("/api/microprojects", json={"name": "Intrus", "area": "projet", "thematic": "ta"}).status_code == 422


def test_a_microproject_belongs_to_the_team_of_its_thematic(client):
    world = _world(client)
    login(client, world.admin)
    body = get_microproject(client, "mp-a")
    assert (body["team"]["slug"], body["thematic"]["slug"], body["role_source"]) == ("equipe-a", "ta", "admin")
    login(client, world.manager_a)
    assert get_microproject(client, "mp-a")["role_source"] == "membership"  # il l'a créé
    assert list_microprojects(client, area="projet") == [get_microproject(client, "mp-a")]
    # un membre de B ne crée pas dans la thématique de A, même invité (voir plus bas) ; l'équipe est celle de la thématique
    mismatch = client.post("/api/microprojects", json={"name": "Autre", "area": "projet", "thematic": "ta", "team": "equipe-b"})
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "team_mismatch"


def test_inviting_a_team_into_a_thematic_lets_it_read_without_writing(client):
    world = _world(client)
    login(client, world.manager_b)
    assert client.post("/api/areas/projet/thematics/ta/teams", json={"team": "equipe-b"}).status_code == 404  # il ne s'invite pas

    login(client, world.manager_a)
    assert invite_team(client, "projet", "ta", "equipe-a").status_code == 409  # l'équipe propriétaire
    assert client.post("/api/areas/projet/thematics/ta/teams", json={"team": "inconnue"}).status_code == 422
    invited = assert_created(invite_team(client, "projet", "ta", "equipe-b"))
    assert [t["slug"] for t in invited["invited_teams"]] == ["equipe-b"]
    assert invite_team(client, "projet", "ta", "equipe-b").status_code == 201  # sans effet

    for email in (world.manager_b, world.member_b):  # toute l'équipe, manager ou non
        login(client, email)
        assert _thematics(client) == ["ta", "tb"]
        thematic = assert_ok(client.get("/api/areas/projet/thematics/ta"))
        assert (thematic["can_manage"], thematic["can_place_microproject"], thematic["team"]["slug"]) == (False, False, "equipe-a")
        body = get_microproject(client, "mp-a")
        assert (body["role"], body["role_source"], body["can_edit"], body["can_manage"]) == ("viewer", "thematic_team", False, False)
        assert client.patch("/api/microprojects/mp-a", json={"description": "x"}).status_code == 403
        assert client.post("/api/microprojects/mp-a/members", json={"email": world.outsider, "role": "viewer"}).status_code == 403
        assert client.patch("/api/areas/projet/thematics/ta", json={"description": "x"}).status_code == 403
        assert client.post("/api/microprojects", json={"name": "Intrus", "area": "projet", "thematic": "ta"}).status_code == 403
        assert {p["slug"] for p in list_microprojects(client, scope="readable")} == {"mp-a", "mp-b"}
        assert {p["slug"] for p in list_microprojects(client)} == {"mp-b"}  # « mes » µprojets : ceux de mon équipe seulement

    login(client, world.manager_a)  # elle retire l'invitation : l'équipe B ne voit plus rien
    assert assert_ok(client.delete("/api/areas/projet/thematics/ta/teams/equipe-b"))["invited_teams"] == []
    assert client.delete("/api/areas/projet/thematics/ta/teams/equipe-b").status_code == 404
    login(client, world.member_b)
    assert _thematics(client) == ["tb"]
    assert client.get("/api/microprojects/mp-a").status_code == 403


def test_someone_added_to_a_microproject_sees_its_thematic_and_reads_the_others(client):
    world = _world(client)
    login(client, world.manager_a)
    create_microproject(client, "MP A2", area="projet", thematic="ta")
    add_member(client, "mp-a", world.outsider, "editor")  # n'importe qui de l'application, d'aucune équipe

    login(client, world.outsider)
    assert _thematics(client) == ["ta"]  # la thématique de ce µprojet, pas celle de B
    own = get_microproject(client, "mp-a")
    assert (own["role"], own["role_source"], own["can_edit"]) == ("editor", "membership", True)
    other = get_microproject(client, "mp-a2")  # un autre µprojet de la thématique : en lecture
    assert (other["role"], other["role_source"], other["can_edit"]) == ("viewer", "thematic_guest", False)
    assert client.patch("/api/microprojects/mp-a2", json={"description": "x"}).status_code == 403
    assert client.get("/api/microprojects/mp-b").status_code == 403
    assert client.get("/api/areas/projet/thematics/tb").status_code == 404
    assert launch(client, "mp-a", title="Essai", intent="Vérifier")["id"]  # ce qu'un éditeur fait, il le fait là
    assert client.post("/api/microprojects", json={"name": "Chez A", "area": "projet", "thematic": "ta"}).status_code == 403  # pas de l'équipe A
    assert {p["slug"] for p in list_microprojects(client, scope="readable")} == {"mp-a", "mp-a2"}
    assert {p["slug"] for p in list_microprojects(client)} == {"mp-a"}  # il n'est membre que de celui-là

    login(client, world.manager_a)  # retiré du µprojet, il ne voit plus la thématique
    login_id = next(m["id"] for m in assert_ok(client.get("/api/microprojects/mp-a/members")) if m["email"] == world.outsider)
    assert client.delete(f"/api/microprojects/mp-a/members/{login_id}").status_code == 204
    login(client, world.outsider)
    assert _thematics(client) == []


def test_the_team_of_a_thematic_or_a_microproject_is_asked_when_several_fit(client):
    world = _world(client)
    login(client, world.both)  # manager de A et de B
    ambiguous = client.post("/api/areas/projet/thematics", json={"name": "TC"})
    assert ambiguous.status_code == 422 and ambiguous.json()["code"] == "team_required"
    assert client.post("/api/areas/projet/thematics", json={"name": "TC", "team": "equipe-b"}).status_code == 201
    assert client.post("/api/areas/projet/thematics", json={"name": "TD", "team": "inconnue"}).status_code == 422
    area = get_area(client, "projet")
    assert [t["slug"] for t in area["manageable_teams"]] == ["equipe-a", "equipe-b"]
    assert [t["slug"] for t in area["placement_teams"]] == ["equipe-a", "equipe-b"]

    # hors thématique, le µprojet appartient à l'une des équipes du projet de son créateur
    needs = client.post("/api/microprojects", json={"name": "Libre", "area": "projet"})
    assert needs.status_code == 422 and needs.json()["code"] == "team_required"
    chosen = assert_created(client.post("/api/microprojects", json={"name": "Libre", "area": "projet", "team": "equipe-a"}))
    assert chosen["team"]["slug"] == "equipe-a" and chosen["thematic"] is None
    assert client.post("/api/microprojects", json={"name": "Libre 2", "area": "projet", "team": "inconnue"}).status_code == 422

    login(client, world.manager_b)  # une seule équipe : sans choix
    assert create_microproject(client, "Libre B", area="projet")["team"]["slug"] == "equipe-b"
    assert client.post("/api/microprojects", json={"name": "Chez A", "area": "projet", "team": "equipe-a"}).status_code == 403

    login(client, world.admin)  # un admin choisit parmi celles du projet
    assert client.post("/api/microprojects", json={"name": "Admin", "area": "projet"}).json()["code"] == "team_required"


def test_a_member_of_a_team_without_thematic_sees_its_microprojects_outside_any_thematic(client):
    """Un µprojet hors thématique est celui de son équipe : ses membres le lisent, pas les autres."""
    world = _world(client)
    login(client, world.manager_b)
    create_microproject(client, "Libre B", area="projet")
    login(client, world.member_b)
    assert get_microproject(client, "libre-b")["role_source"] == "team"
    login(client, world.manager_a)
    assert client.get("/api/microprojects/libre-b").status_code == 403
    assert "libre-b" not in {row["microproject"]["slug"] for row in assert_ok(client.get("/api/experiment-stats"))}
