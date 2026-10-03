"""Les membres d'un µprojet : ajouter un compte existant, changer son rôle, le retirer - avec les
deux invariants (au moins un propriétaire ; le créateur le reste), au changement de rôle comme au
retrait."""

from __future__ import annotations

import sqlite3

from support.accounts import login, signup
from support.http import assert_handler_404
from support.microprojects import add_member, invitations, members, remove_member, set_member_role, signup_with_microproject


def _owner_and(client, *emails):
    """Le µprojet de owner@ (connecté à la fin) et les comptes ``emails``, créés au passage."""
    slug = signup_with_microproject(client, "owner@example.com", name="Owner")
    accounts = [signup(client, email, name=email.split("@")[0]) for email in emails]
    login(client, "owner@example.com")
    return slug, accounts


def test_adding_an_existing_account(client, outbox):
    slug, [bob] = _owner_and(client, "bob@example.com")
    response = client.post(f"/api/microprojects/{slug}/members", json={"email": " Bob@Example.com ", "role": "editor"})
    assert response.status_code == 201
    assert response.headers["location"] == f"/api/microprojects/{slug}/members/{bob['id']}"
    assert response.json() == {"id": bob["id"], "name": "bob", "email": "bob@example.com", "role": "editor", "is_creator": False}
    located = client.get(response.headers["location"])  # le Location se lit
    assert located.status_code == 200 and located.json() == response.json()
    assert outbox == []  # un compte existant n'est pas invité : il est ajouté

    listed = {m["email"]: (m["role"], m["is_creator"]) for m in members(client, slug)}
    assert listed == {"owner@example.com": ("owner", True), "bob@example.com": ("editor", False)}


def test_adding_an_address_without_account_is_a_404_no_account(client, outbox):
    slug, _ = _owner_and(client)
    response = client.post(f"/api/microprojects/{slug}/members", json={"email": "nouveau@example.com", "role": "editor"})
    assert_handler_404(response, "invitez")
    assert response.json()["code"] == "no_account"
    assert outbox == [] and invitations(client, slug) == []  # rien n'est envoyé sans le second appel


def test_adding_a_member_twice_is_a_conflict(client):
    slug, _ = _owner_and(client, "bob@example.com")
    add_member(client, slug, "bob@example.com", "viewer")
    again = client.post(f"/api/microprojects/{slug}/members", json={"email": "bob@example.com", "role": "owner"})
    assert again.status_code == 409 and again.json()["code"] == "already_member"
    assert [m["role"] for m in members(client, slug) if m["email"] == "bob@example.com"] == ["viewer"]  # pas d'upsert


def test_an_unknown_role_is_refused(client):
    slug, [bob] = _owner_and(client, "bob@example.com")
    assert client.post(f"/api/microprojects/{slug}/members", json={"email": "bob@example.com", "role": "admin"}).status_code == 422
    add_member(client, slug, "bob@example.com")
    assert set_member_role(client, slug, bob["id"], "chef").status_code == 422


def test_changing_a_role(client):
    slug, [bob] = _owner_and(client, "bob@example.com")
    add_member(client, slug, "bob@example.com", "viewer")

    promoted = set_member_role(client, slug, bob["id"], "owner")
    assert promoted.status_code == 200 and promoted.json()["role"] == "owner"
    unchanged = set_member_role(client, slug, bob["id"], "owner")
    assert unchanged.status_code == 200 and unchanged.json()["role"] == "owner"
    assert set_member_role(client, slug, bob["id"], "editor").json()["role"] == "editor"  # il reste owner@
    assert_handler_404(set_member_role(client, slug, 999, "editor"), "membre")


def test_the_creator_stays_an_owner(client):
    slug, [bob] = _owner_and(client, "bob@example.com")
    owner = members(client, slug)[0]
    add_member(client, slug, "bob@example.com", "owner")

    # même avec un autre propriétaire : ni rétrogradé, ni retiré
    login(client, "bob@example.com")
    for response in (set_member_role(client, slug, owner["id"], "editor"), remove_member(client, slug, owner["id"])):
        assert response.status_code == 409 and response.json()["code"] == "creator_protected"
    assert {m["email"]: m["role"] for m in members(client, slug)}["owner@example.com"] == "owner"


def test_a_microproject_keeps_at_least_one_owner(client, data_dir):
    slug, [bob, carol] = _owner_and(client, "bob@example.com", "carol@example.com")
    add_member(client, slug, "bob@example.com", "owner")
    add_member(client, slug, "carol@example.com", "editor")
    # un µprojet d'avant, dont le créateur a été rétrogradé : bob est son seul propriétaire
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute("UPDATE memberships SET role = 'editor' WHERE user_id = (SELECT id FROM users WHERE email = 'owner@example.com')")
    conn.commit()
    conn.close()

    login(client, "bob@example.com")
    for response in (set_member_role(client, slug, bob["id"], "viewer"), remove_member(client, slug, bob["id"])):
        assert response.status_code == 409 and response.json()["code"] == "last_owner"
    # un second propriétaire, et bob peut partir
    assert set_member_role(client, slug, carol["id"], "owner").status_code == 200
    assert remove_member(client, slug, bob["id"]).status_code == 204
    login(client, "carol@example.com")
    assert {m["email"] for m in members(client, slug)} == {"owner@example.com", "carol@example.com"}


def test_removing_a_member(client):
    slug, [bob] = _owner_and(client, "bob@example.com")
    add_member(client, slug, "bob@example.com", "editor")

    response = remove_member(client, slug, bob["id"])
    assert response.status_code == 204 and response.content == b""
    assert [m["email"] for m in members(client, slug)] == ["owner@example.com"]
    assert_handler_404(remove_member(client, slug, bob["id"]), "membre")
    assert_handler_404(client.get(f"/api/microprojects/{slug}/members/{bob['id']}"), "membre")

    login(client, "bob@example.com")
    assert client.get(f"/api/microprojects/{slug}").status_code == 403


def test_an_owner_may_leave_when_another_owner_remains(client):
    slug, [bob] = _owner_and(client, "bob@example.com")
    add_member(client, slug, "bob@example.com", "owner")
    login(client, "bob@example.com")
    assert remove_member(client, slug, bob["id"]).status_code == 204
    assert client.get(f"/api/microprojects/{slug}").status_code == 403
