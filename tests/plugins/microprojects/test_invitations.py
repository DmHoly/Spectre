from __future__ import annotations

from support.accounts import link_token, login, signup
from support.http import assert_handler_404
from support.microprojects import add_member, signup_with_microproject


def _owner_microproject(client, microproject_name="Projet"):
    return signup_with_microproject(client, "owner@example.com", microproject_name, name="Owner")


def _invite(client, outbox, slug, email, role):
    add_member(client, slug, email, role)
    assert outbox[-1].to == email
    return link_token(outbox[-1].body, "invitation")


def test_invite_unknown_email_creates_invitation(client, outbox):
    slug = _owner_microproject(client)
    response = client.post(f"/api/microprojets/{slug}/members", json={"email": "nouveau@example.com", "role": "editor"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "invited"
    assert any(inv["email"] == "nouveau@example.com" for inv in body["invitations"])

    [email] = outbox
    assert email.to == "nouveau@example.com" and "Projet" in email.subject
    assert "/inscription?invitation=" in email.body


def test_invite_existing_account_adds_directly(client, outbox):
    slug = _owner_microproject(client)
    signup(client, "existe@example.com", name="Existe")
    login(client, "owner@example.com")

    response = client.post(f"/api/microprojets/{slug}/members", json={"email": "existe@example.com", "role": "viewer"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "added"
    assert any(m["email"] == "existe@example.com" for m in body["members"])
    assert body["invitations"] == []
    assert outbox == []  # no e-mail: the account already exists


def test_owner_can_cancel_invitation(client, outbox):
    slug = _owner_microproject(client)
    token = _invite(client, outbox, slug, "annuler@example.com", "viewer")

    response = client.delete(f"/api/microprojets/{slug}/invitations/{token}")
    assert response.status_code == 200
    assert response.json() == []
    assert_handler_404(client.get(f"/api/invitations/{token}"))


def test_invalid_invitation_token_404s(client):
    assert_handler_404(client.get("/api/invitations/not-a-real-token"), "invitation")
