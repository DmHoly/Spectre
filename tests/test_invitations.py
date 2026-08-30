from __future__ import annotations

import logging


def _create_project(client, email="owner@example.com", name="Owner", project_name="Projet"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def _extract_invitation_token(caplog) -> str:
    log_text = "\n".join(r.message for r in caplog.records)
    assert "/inscription?invitation=" in log_text
    return log_text.split("invitation=")[1].split()[0].strip()


def test_invite_unknown_email_creates_invitation(client, caplog):
    slug = _create_project(client)
    with caplog.at_level(logging.WARNING, logger="spectre.email"):
        response = client.post(f"/api/projects/{slug}/members", json={"email": "nouveau@example.com", "role": "editor"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "invited"
    assert any(inv["email"] == "nouveau@example.com" for inv in body["invitations"])
    assert "/inscription?invitation=" in "\n".join(r.message for r in caplog.records)


def test_invite_existing_account_adds_directly(client):
    slug = _create_project(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "existe@example.com", "password": "supersecret", "name": "Existe"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner@example.com", "password": "supersecret"})

    response = client.post(f"/api/projects/{slug}/members", json={"email": "existe@example.com", "role": "viewer"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "added"
    assert any(m["email"] == "existe@example.com" for m in body["members"])
    assert body["invitations"] == []


def test_registering_with_matching_invitation_joins_project(client, caplog):
    slug = _create_project(client, project_name="Salle blanche")
    with caplog.at_level(logging.WARNING, logger="spectre.email"):
        client.post(f"/api/projects/{slug}/members", json={"email": "invite@example.com", "role": "editor"})
    token = _extract_invitation_token(caplog)

    info = client.get(f"/api/auth/invitation/{token}")
    assert info.status_code == 200
    assert info.json() == {"email": "invite@example.com", "project_name": "Salle blanche"}

    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={"email": "invite@example.com", "password": "supersecret", "name": "Invite", "invitation": token},
    )
    assert response.status_code == 201
    assert response.json()["joined_project"] == "Salle blanche"

    project = client.get(f"/api/projects/{slug}").json()
    assert project["role"] == "editor"


def test_registering_with_wrong_email_does_not_consume_invitation(client, caplog):
    slug = _create_project(client)
    with caplog.at_level(logging.WARNING, logger="spectre.email"):
        client.post(f"/api/projects/{slug}/members", json={"email": "correct@example.com", "role": "viewer"})
    token = _extract_invitation_token(caplog)

    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/register",
        json={"email": "different@example.com", "password": "supersecret", "name": "Autre", "invitation": token},
    )
    assert response.status_code == 201
    assert response.json()["joined_project"] is None

    # the invitation is still there, addressed to the original e-mail
    info = client.get(f"/api/auth/invitation/{token}")
    assert info.json()["email"] == "correct@example.com"


def test_owner_can_cancel_invitation(client, caplog):
    slug = _create_project(client)
    with caplog.at_level(logging.WARNING, logger="spectre.email"):
        client.post(f"/api/projects/{slug}/members", json={"email": "annuler@example.com", "role": "viewer"})
    token = _extract_invitation_token(caplog)

    response = client.delete(f"/api/projects/{slug}/invitations/{token}")
    assert response.status_code == 200
    assert response.json() == []
    assert client.get(f"/api/auth/invitation/{token}").status_code == 404


def test_invalid_invitation_token_404s(client):
    assert client.get("/api/auth/invitation/not-a-real-token").status_code == 404
