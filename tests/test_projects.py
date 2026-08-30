from __future__ import annotations


def register_and_login(client, email, name="Test", password="supersecret"):
    client.post("/api/auth/register", json={"email": email, "password": password, "name": name})


def test_create_project_makes_creator_owner(client):
    register_and_login(client, "owner@example.com", "Owner")
    response = client.post("/api/projects", json={"name": "Couches minces", "description": "Salle blanche 2"})
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "couches-minces"
    assert body["role"] == "owner"
    assert body["running_count"] == 0

    listed = client.get("/api/projects").json()
    assert len(listed) == 1
    assert listed[0]["slug"] == "couches-minces"


def test_slug_collision_gets_suffixed(client):
    register_and_login(client, "owner@example.com", "Owner")
    client.post("/api/projects", json={"name": "Couches minces"})
    second = client.post("/api/projects", json={"name": "Couches minces"})
    assert second.json()["slug"] == "couches-minces-2"


def test_nonexistent_project_is_404(client):
    register_and_login(client, "owner@example.com", "Owner")
    response = client.get("/api/projects/does-not-exist")
    assert response.status_code == 404


def test_project_requires_authentication(client):
    response = client.get("/api/projects")
    assert response.status_code == 401
