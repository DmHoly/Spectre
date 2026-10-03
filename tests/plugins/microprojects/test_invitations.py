"""Les invitations d'un µprojet, côté propriétaire : inviter une adresse (un e-mail part avec le
lien), lister celles en attente - sans leur jeton -, les annuler par leur id. Le jeton n'est gardé
que haché."""

from __future__ import annotations

import sqlite3

from support.accounts import link_token, login, signup
from support.http import assert_handler_404
from support.microprojects import add_member, invitations, invite, invite_and_get_token, signup_with_microproject


def _owner_microproject(client, microproject_name="Projet"):
    return signup_with_microproject(client, "owner@example.com", microproject_name, name="Owner")


def test_inviting_an_address_sends_the_link_by_email(client, outbox):
    slug = _owner_microproject(client)
    response = client.post(f"/api/microprojects/{slug}/invitations", json={"email": "Nouveau@Example.com", "role": "editor"})
    assert response.status_code == 201
    invitation = response.json()
    assert set(invitation) == {"id", "email", "role", "created_at", "expires_at"}  # jamais le jeton
    assert (invitation["email"], invitation["role"]) == ("nouveau@example.com", "editor")

    [email] = outbox
    assert email.to == "nouveau@example.com" and "Projet" in email.subject
    assert "Owner" in email.body and "/inscription?invitation=" in email.body
    token = link_token(email.body, "invitation")
    assert client.get(f"/api/invitations/{token}").json()["email"] == "nouveau@example.com"

    assert invitations(client, slug) == [invitation]


def test_the_token_is_stored_hashed(client, outbox, data_dir):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "nouveau@example.com")
    conn = sqlite3.connect(data_dir / "spectre.db")
    stored = conn.execute("SELECT * FROM invitations").fetchall()
    conn.close()
    assert len(stored) == 1 and not any(token in str(value) for value in stored[0])


def test_inviting_again_replaces_the_pending_invitation(client, outbox):
    slug = _owner_microproject(client)
    first = invite_and_get_token(client, outbox, slug, "bob@example.com", "viewer")
    second = invite_and_get_token(client, outbox, slug, "bob@example.com", "owner")

    assert [(i["email"], i["role"]) for i in invitations(client, slug)] == [("bob@example.com", "owner")]
    assert_handler_404(client.get(f"/api/invitations/{first}"))
    assert client.get(f"/api/invitations/{second}").status_code == 200


def test_a_member_is_not_invited(client, outbox):
    slug = _owner_microproject(client)
    signup(client, "bob@example.com")
    login(client, "owner@example.com")
    add_member(client, slug, "bob@example.com")

    for email in ("bob@example.com", "owner@example.com"):
        response = client.post(f"/api/microprojects/{slug}/invitations", json={"email": email, "role": "editor"})
        assert response.status_code == 409 and response.json()["code"] == "already_member"
    assert outbox == []


def test_an_existing_account_may_be_invited(client, outbox):
    # inviter (un lien à accepter) plutôt qu'ajouter directement : la personne choisit de rejoindre
    slug = _owner_microproject(client)
    signup(client, "bob@example.com")
    login(client, "owner@example.com")
    token = invite_and_get_token(client, outbox, slug, "bob@example.com")
    assert client.get(f"/api/invitations/{token}").json()["account_exists"] is True


def test_an_invalid_address_or_role_is_refused(client, outbox):
    slug = _owner_microproject(client)
    url = f"/api/microprojects/{slug}/invitations"
    assert client.post(url, json={"email": "pas-une-adresse", "role": "viewer"}).json()["code"] == "invalid_email"
    assert client.post(url, json={"email": "x@example.com", "role": "admin"}).status_code == 422
    assert outbox == [] and invitations(client, slug) == []


def test_owner_can_cancel_invitation(client, outbox):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "annuler@example.com", "viewer")
    [invitation] = invitations(client, slug)

    response = client.delete(f"/api/microprojects/{slug}/invitations/{invitation['id']}")
    assert response.status_code == 204 and response.content == b""
    assert invitations(client, slug) == []
    assert_handler_404(client.get(f"/api/invitations/{token}"))
    assert_handler_404(client.delete(f"/api/microprojects/{slug}/invitations/{invitation['id']}"), "invitation")


def test_an_invitation_is_cancelled_only_from_its_microproject(client, outbox):
    slug = _owner_microproject(client)
    other = signup_with_microproject(client, "owner2@example.com", "Autre", name="Owner 2")
    login(client, "owner@example.com")
    invite(client, slug, "bob@example.com")
    [invitation] = invitations(client, slug)

    login(client, "owner2@example.com")
    assert_handler_404(client.delete(f"/api/microprojects/{other}/invitations/{invitation['id']}"), "invitation")
    login(client, "owner@example.com")
    assert len(invitations(client, slug)) == 1


def test_expired_invitations_are_not_listed(client, outbox, data_dir):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "tard@example.com")
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute("UPDATE invitations SET expires_at = datetime('now', '-1 day')")
    conn.commit()
    conn.close()
    assert invitations(client, slug) == []
    assert_handler_404(client.get(f"/api/invitations/{token}"))


def test_invalid_invitation_token_404s(client):
    assert_handler_404(client.get("/api/invitations/not-a-real-token"), "invitation")
