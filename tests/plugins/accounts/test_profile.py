from __future__ import annotations

from support.accounts import login, me, signup


def test_update_profile_name(client):
    signup(client, "profile@example.com", name="Ancien Nom")
    response = client.patch("/api/users/me", json={"name": "Nouveau Nom"})
    assert response.status_code == 200
    assert response.json()["name"] == "Nouveau Nom"
    assert me(client)["name"] == "Nouveau Nom"


def test_update_profile_without_fields_changes_nothing(client):
    signup(client, "profile3@example.com", name="Inchangé")
    response = client.patch("/api/users/me", json={})
    assert response.status_code == 200
    assert response.json()["name"] == "Inchangé"


def test_update_profile_rejects_empty_name(client):
    signup(client, "profile2@example.com", name="X")
    response = client.patch("/api/users/me", json={"name": "   "})
    assert response.status_code == 422


def test_change_password_with_a_wrong_current_password_is_a_422_and_keeps_the_session(client):
    signup(client, "pw@example.com", name="P")
    response = client.put("/api/users/me/password", json={"current_password": "wrong", "new_password": "nouveaumdp123"})
    # never 401: the front would take it for an expired session and log the user out
    assert response.status_code == 422
    assert response.json() == {"detail": "mot de passe actuel incorrect", "code": "invalid_current_password"}
    assert me(client)["email"] == "pw@example.com"


def test_change_password_rejects_a_short_new_password(client):
    signup(client, "pw3@example.com", name="P3")
    response = client.put("/api/users/me/password", json={"current_password": "supersecret", "new_password": "court"})
    assert response.status_code == 422
    assert response.json()["code"] == "weak_password"


def test_change_password_signs_out_everywhere(client):
    signup(client, "pw2@example.com", name="P2")
    response = client.put("/api/users/me/password", json={"current_password": "supersecret", "new_password": "nouveaumdp123"})
    assert response.status_code == 204 and response.content == b""

    # the very session that changed the password is now dead too
    assert client.get("/api/users/me").status_code == 401

    assert client.post("/api/sessions", json={"email": "pw2@example.com", "password": "supersecret"}).status_code == 422
    login(client, "pw2@example.com", "nouveaumdp123")
