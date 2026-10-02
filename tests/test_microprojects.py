from __future__ import annotations

from support.accounts import signup
from support.experiments import launch, track_entities
from support.http import assert_handler_404
from support.microprojects import create_microproject, signup_with_microproject


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


def test_entity_history_is_empty_for_a_microproject_with_no_tracked_entities(client):
    slug = signup_with_microproject(client, "hist-empty@example.com", name="Owner")
    history = client.get(f"/api/microprojets/{slug}/entites/historique").json()
    assert history == {"sample_ids": [], "locations": [], "fdls": []}


def test_entity_history_collects_distinct_values_across_experiences(client):
    slug = signup_with_microproject(client, "hist@example.com", name="Owner")

    launch(client, slug, title="A", intent="x", entities=[{"sample_id": "W1-A1", "location": "congélateur B"}])
    second = launch(client, slug, title="B", intent="x", entities=[{"sample_id": "W1-A2", "location": "congélateur B"}])
    # a repeated value (même emplacement) doit rester unique dans l'historique
    track_entities(client, slug, second["id"], [{"sample_id": "W1-A2", "location": "congélateur B"}])

    history = client.get(f"/api/microprojets/{slug}/entites/historique").json()
    assert history == {"sample_ids": ["W1-A1", "W1-A2"], "locations": ["congélateur B"], "fdls": []}
