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


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [{"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": 20, "unit": "nm"}}]


def test_entity_history_is_empty_for_a_project_with_no_tracked_entities(client):
    register_and_login(client, "hist-empty@example.com", "Owner")
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    history = client.get(f"/api/projects/{slug}/entites/historique").json()
    assert history == {"sample_ids": [], "locations": []}


def test_entity_history_collects_distinct_values_across_experiences(client):
    register_and_login(client, "hist@example.com", "Owner")
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]

    client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "A", "intent": "x", "entities": [{"sample_id": "W1-A1", "location": "congélateur B"}]},
    )
    second = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "B", "intent": "x", "entities": [{"sample_id": "W1-A2", "location": "congélateur B"}]},
    ).json()
    # a repeated value (même emplacement) doit rester unique dans l'historique
    client.post(f"/api/projects/{slug}/experiences/{second['id']}/entites", json={"entities": [{"sample_id": "W1-A2", "location": "congélateur B"}]})

    history = client.get(f"/api/projects/{slug}/entites/historique").json()
    assert history == {"sample_ids": ["W1-A1", "W1-A2"], "locations": ["congélateur B"]}
