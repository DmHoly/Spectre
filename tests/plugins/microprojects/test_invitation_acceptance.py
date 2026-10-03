"""L'autre bout d'un e-mail d'invitation : la lire sans session (``GET /api/invitations/{token}``),
puis l'accepter une fois connecté (``POST /api/invitations/{token}/acceptance``) - avec un compte
tout juste créé, ou avec un compte qui existait déjà (la « deuxième invitation » d'une personne
inscrite entre-temps n'est plus morte)."""

from __future__ import annotations

import sqlite3

from support.accounts import login, logout, signup
from support.http import assert_handler_404
from support.microprojects import add_member, get_microproject, invitations, invite_and_get_token, signup_with_microproject


def _owner_microproject(client, microproject_name="Projet"):
    return signup_with_microproject(client, "owner@example.com", microproject_name, name="Owner")


def _accept(client, token):
    return client.post(f"/api/invitations/{token}/acceptance")


def _role_in(client, slug):
    """Le rôle du compte connecté dans le µprojet."""
    return get_microproject(client, slug)["role"]


def test_registering_then_accepting_joins_the_microproject(client, outbox):
    slug = _owner_microproject(client, "Salle blanche")
    token = invite_and_get_token(client, outbox, slug, "invite@example.com", "editor")

    logout(client)
    info = client.get(f"/api/invitations/{token}")
    assert info.status_code == 200
    assert info.json() == {"email": "invite@example.com", "microproject_name": "Salle blanche", "account_exists": False}

    user = signup(client, "invite@example.com", name="Invite")
    response = _accept(client, token)
    assert response.status_code == 201
    assert response.headers["location"] == f"/api/microprojects/{slug}/members/{user['id']}"
    assert response.json() == {"microproject": {"slug": slug, "name": "Salle blanche"}, "role": "editor"}
    assert _role_in(client, slug) == "editor"
    membership = client.get(response.headers["location"])  # le Location se lit
    assert membership.status_code == 200 and membership.json()["role"] == "editor"

    # one-time use
    assert_handler_404(_accept(client, token), "invitation")
    assert_handler_404(client.get(f"/api/invitations/{token}"))
    login(client, "owner@example.com")
    assert invitations(client, slug) == []


def test_signing_up_no_longer_consumes_an_invitation(client, outbox):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "later@example.com", "viewer")

    signup(client, "later@example.com", name="Plus tard")
    # the account exists now: the page offers to sign in, the invitation still waits
    assert client.get(f"/api/invitations/{token}").json()["account_exists"] is True


def test_accepting_with_another_address_is_refused_and_keeps_the_invitation(client, outbox):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "correct@example.com", "viewer")

    signup(client, "different@example.com", name="Autre")
    response = _accept(client, token)
    assert response.status_code == 403
    assert response.json()["code"] == "email_mismatch"

    # the invitation is still there, addressed to the original e-mail
    assert client.get(f"/api/invitations/{token}").json()["email"] == "correct@example.com"


def test_a_second_invitation_is_accepted_with_the_existing_account(client, outbox):
    first = _owner_microproject(client, "Premier")
    second = signup_with_microproject(client, "owner2@example.com", "Second", name="Owner 2")
    login(client, "owner@example.com")
    first_token = invite_and_get_token(client, outbox, first, "twice@example.com", "viewer")
    login(client, "owner2@example.com")
    second_token = invite_and_get_token(client, outbox, second, "twice@example.com", "editor")

    # signs up from the first invitation...
    signup(client, "twice@example.com", name="Deux fois")
    assert _accept(client, first_token).status_code == 201
    # ...then signs in (the account exists) and accepts the second one
    logout(client)
    login(client, "twice@example.com")
    assert _accept(client, second_token).json()["microproject"]["slug"] == second
    assert _role_in(client, first) == "viewer"
    assert _role_in(client, second) == "editor"


def test_accepting_requires_a_session(client, outbox):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "anon@example.com", "viewer")
    logout(client)
    assert _accept(client, token).status_code == 401


def test_accepting_an_unknown_invitation_404s(client):
    signup(client, "someone@example.com", name="S")
    assert_handler_404(_accept(client, "not-a-real-token"), "invitation")


def test_a_stale_invitation_never_lowers_a_role(client, outbox, data_dir):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "bob@example.com", "viewer")
    bob = signup(client, "bob@example.com", name="Bob")
    # une adhésion d'avant, qui n'avait pas consommé l'invitation (l'API, elle, la supprime)
    conn = sqlite3.connect(data_dir / "spectre.db")
    conn.execute("INSERT INTO memberships (microproject_id, user_id, role) SELECT id, ?, 'owner' FROM microprojects", (bob["id"],))
    conn.commit()
    conn.close()

    response = _accept(client, token)
    assert response.status_code == 201 and response.json()["role"] == "owner"
    assert _role_in(client, slug) == "owner"


def test_adding_a_member_directly_drops_their_pending_invitations(client, outbox):
    slug = _owner_microproject(client)
    token = invite_and_get_token(client, outbox, slug, "bob@example.com", "viewer")
    signup(client, "bob@example.com", name="Bob")

    login(client, "owner@example.com")
    add_member(client, slug, "bob@example.com", "owner")
    assert invitations(client, slug) == []

    login(client, "bob@example.com")
    assert_handler_404(_accept(client, token), "invitation")
    assert _role_in(client, slug) == "owner"
