"""Le compte administrateur initial et la réinitialisation d'un mot de passe oublié par un admin."""

from __future__ import annotations

from fastapi.testclient import TestClient

from support.accounts import login, logout, signup


def test_initial_admin_is_created_on_an_empty_database_and_must_change_its_password(data_dir, monkeypatch):
    monkeypatch.setenv("SPECTRE_INITIAL_ADMIN", "admin:admin")
    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:
        user = login(client, "admin", "admin")
        assert user["is_admin"] is True and user["must_change_password"] is True

        # tout est fermé (403) sauf le profil et le changement de mot de passe
        blocked = client.get("/api/users")
        assert blocked.status_code == 403 and blocked.json()["code"] == "password_change_required"
        assert client.get("/api/users/me").status_code == 200

        response = client.put("/api/users/me/password", json={"current_password": "admin", "new_password": "nouveau-mdp-1"})
        assert response.status_code == 204
        login(client, "admin", "nouveau-mdp-1")
        assert client.get("/api/users").status_code == 200


def test_initial_admin_is_not_created_when_an_account_exists(data_dir, monkeypatch):
    from spectre.kernel.app import create_app

    with TestClient(create_app()) as client:
        signup(client, "premier@example.com")
        logout(client)
    monkeypatch.setenv("SPECTRE_INITIAL_ADMIN", "admin:admin")
    # la migration est déjà passée sur cette base : aucun compte « admin » n'apparaît
    with TestClient(create_app()) as client:
        assert client.post("/api/sessions", json={"email": "admin", "password": "admin"}).status_code == 422


def test_admin_resets_a_password_and_the_user_must_choose_a_new_one(client):
    signup(client, "admin@example.com", name="Admin")  # le premier compte est l'administrateur
    member = signup(client, "membre@example.com", name="Membre")
    admin = login(client, "admin@example.com")

    users = client.get("/api/users")
    assert users.status_code == 200 and {u["email"] for u in users.json()} == {"admin@example.com", "membre@example.com"}

    reset = client.post(f"/api/users/{member['id']}/password-resets")
    assert reset.status_code == 201
    temporary = reset.json()["temporary_password"]
    assert reset.json()["user"]["must_change_password"] is True

    # l'ancien mot de passe ne marche plus, le provisoire oui - mais tout est fermé jusqu'au changement
    assert client.post("/api/sessions", json={"email": "membre@example.com", "password": "supersecret"}).status_code == 422
    logout(client)
    login(client, "membre@example.com", temporary)
    assert client.get("/api/users/me").json()["must_change_password"] is True
    assert client.get("/api/microprojects").status_code == 403

    response = client.put("/api/users/me/password", json={"current_password": temporary, "new_password": "choisi-par-lui-1"})
    assert response.status_code == 204
    login(client, "membre@example.com", "choisi-par-lui-1")
    assert client.get("/api/users/me").json()["must_change_password"] is False
    assert client.get("/api/microprojects").status_code == 200
    assert admin["is_admin"] is True


def test_reset_is_for_admins_only_and_never_on_oneself(client):
    admin = signup(client, "admin@example.com", name="Admin")
    member = signup(client, "membre@example.com", name="Membre")

    assert client.get("/api/users").status_code == 403
    assert client.post(f"/api/users/{admin['id']}/password-resets").status_code == 403

    login(client, "admin@example.com")
    assert client.post(f"/api/users/{admin['id']}/password-resets").status_code == 409
    assert client.post("/api/users/9999/password-resets").status_code == 404
    assert client.post(f"/api/users/{member['id']}/password-resets").status_code == 201
