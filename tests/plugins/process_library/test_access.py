"""Qui modifie un élément partagé de la bibliothèque : son auteur, un administrateur, et ceux à qui
l'auteur donne la main - des comptes (par adresse) ou des équipes ; la bibliothèque s'écrit sans µprojet."""

from __future__ import annotations

import pytest

from support.accounts import login, signup
from support.process_library import BODIES, COLLECTIONS, create_item, get_item, update_item
from support.teams import add_team_member, create_team

pytestmark = pytest.mark.parametrize("collection", COLLECTIONS)


def _put_editors(client, collection, item_id, **body):
    return client.put(f"/api/{collection}/{item_id}/editors", json=body)


def _shared(client, collection, name="Commun"):
    """admin (premier compte), auteur, ami, equipier, tiers - le client reste sur l'auteur."""
    for who in ("admin", "auteur", "ami", "equipier", "tiers"):
        signup(client, f"{who}@example.com", name=who.capitalize())
    login(client, "auteur@example.com")
    return create_item(client, collection, BODIES[collection](name), scope="shared")


def test_a_shared_item_is_created_without_a_microproject_and_names_its_owner(client, collection):
    item = _shared(client, collection)
    created = client.post(f"/api/{collection}", json=BODIES[collection]("Sans scope"))
    assert created.status_code == 201
    assert (created.json()["scope"], created.json()["microproject"]) == ("shared", None)
    assert item["created_by"]["name"] == "Auteur"
    assert (item["can_edit"], item["can_manage_access"]) == (True, True)
    assert (item["owner_teams"], item["editors"], item["editor_teams"]) == ([], [], [])


def test_the_owner_gives_edit_rights_to_an_account(client, collection):
    item = _shared(client, collection)
    granted = _put_editors(client, collection, item["id"], emails=["ami@example.com"])
    assert granted.status_code == 200
    assert [e["email"] for e in granted.json()["editors"]] == ["ami@example.com"]

    login(client, "ami@example.com")
    seen = get_item(client, collection, item["id"])
    assert (seen["can_edit"], seen["can_manage_access"]) == (True, False)
    assert update_item(client, collection, item["id"], name="Renomme")["name"] == "Renomme"
    assert client.delete(f"/api/{collection}/{item['id']}").status_code == 403  # supprimer reste à l'auteur
    assert _put_editors(client, collection, item["id"], emails=["tiers@example.com"]).status_code == 403

    login(client, "tiers@example.com")
    assert client.patch(f"/api/{collection}/{item['id']}", json={"name": "Non"}).status_code == 403


def test_the_owner_gives_edit_rights_to_a_team(client, collection):
    item = _shared(client, collection)
    login(client, "admin@example.com")
    create_team(client, "Épitaxie")
    add_team_member(client, "epitaxie", "equipier@example.com", "member")
    add_team_member(client, "epitaxie", "auteur@example.com", "member")

    login(client, "auteur@example.com")
    granted = _put_editors(client, collection, item["id"], team_slugs=["epitaxie"])
    assert [t["slug"] for t in granted.json()["editor_teams"]] == ["epitaxie"]
    assert [t["slug"] for t in get_item(client, collection, item["id"])["owner_teams"]] == ["epitaxie"]  # le badge de l'équipe de l'auteur

    login(client, "equipier@example.com")
    assert update_item(client, collection, item["id"], name="Par l'equipe")["name"] == "Par l'equipe"
    login(client, "tiers@example.com")
    assert get_item(client, collection, item["id"])["can_edit"] is False

    login(client, "auteur@example.com")  # retirer l'équipe retire le droit
    _put_editors(client, collection, item["id"], team_slugs=[])
    login(client, "equipier@example.com")
    assert get_item(client, collection, item["id"])["can_edit"] is False


def test_granting_checks_the_account_the_team_and_who_asks(client, collection):
    item = _shared(client, collection)
    unknown = _put_editors(client, collection, item["id"], emails=["personne@example.com"])
    assert (unknown.status_code, unknown.json()["code"]) == (404, "no_account")
    assert _put_editors(client, collection, item["id"], team_slugs=["nulle-part"]).status_code == 404

    login(client, "tiers@example.com")
    assert _put_editors(client, collection, item["id"], emails=["tiers@example.com"]).status_code == 403
    login(client, "admin@example.com")  # un administrateur gère aussi les accès
    assert _put_editors(client, collection, item["id"], emails=["ami@example.com"]).status_code == 200
    builtin = client.get(f"/api/{collection}", params={"scope": "builtin"}).json()
    if builtin:
        assert _put_editors(client, collection, builtin[0]["id"], emails=[]).status_code == 403
