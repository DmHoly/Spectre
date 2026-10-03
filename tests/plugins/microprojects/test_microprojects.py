from __future__ import annotations

from support.accounts import signup
from support.http import assert_handler_404
from support.microprojects import create_microproject


def test_create_microproject_makes_creator_owner(client):
    signup(client, "owner@example.com", name="Owner")
    response = client.post("/api/microprojets", json={"name": "Couches minces", "description": "Salle blanche 2"})
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "couches-minces"
    assert body["role"] == "owner"
    assert body["running_count"] == 0

    listed = client.get("/api/microprojets").json()
    assert len(listed) == 1
    assert listed[0]["slug"] == "couches-minces"


def test_slug_collision_gets_suffixed(client):
    signup(client, "owner@example.com", name="Owner")
    create_microproject(client, "Couches minces")
    assert create_microproject(client, "Couches minces")["slug"] == "couches-minces-2"


def test_nonexistent_microproject_is_404(client):
    signup(client, "owner@example.com", name="Owner")
    assert_handler_404(client.get("/api/microprojets/does-not-exist"), "introuvable")


def test_microproject_requires_authentication(client):
    response = client.get("/api/microprojets")
    assert response.status_code == 401
