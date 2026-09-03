from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": 20, "unit": "nm"},
        }
    ]


def _register_and_project(client, email):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": "Projet"}).json()["slug"]


def test_setting_physical_tracking_on_a_single_experience(client):
    slug = _register_and_project(client, "physical@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W12-A3", "location": "congelateur B"}]},
    )
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert new_id != launched["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{new_id}").json()
    assert detail["physical_tracking"] == [{"sample_id": "W12-A3", "location": "congelateur B"}]
    assert detail["status"] == "draft"  # bookkeeping only, doesn't touch status


def test_physical_tracking_rejects_wrong_entity_count_for_a_single_experience(client):
    slug = _register_and_project(client, "physicalcount@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "A"}, {"sample_id": "B"}]},
    )
    assert response.status_code == 422


def test_physical_tracking_on_a_campaign_matches_entity_count(client):
    slug = _register_and_project(client, "physicalcampaign@example.com")
    campaign = client.post(
        f"/api/projects/{slug}/experiences/campagne",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]},
            "title": "Campagne",
            "intent": "Balayage",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()

    too_few = client.post(
        f"/api/projects/{slug}/experiences/{campaign['id']}/entites",
        json={"entities": [{"sample_id": "A"}]},
    )
    assert too_few.status_code == 422

    ok = client.post(
        f"/api/projects/{slug}/experiences/{campaign['id']}/entites",
        json={"entities": [{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}]},
    )
    assert ok.status_code == 201

    matrix = client.get(f"/api/projects/{slug}/experiences/{ok.json()['id']}/matrice").json()
    assert [e["sample_id"] for e in matrix["physical_tracking"]] == ["A", "B", "C"]


def test_physical_tracking_carries_forward_through_evidence_and_conclude(client):
    slug = _register_and_project(client, "physicalcarry@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "placeholder"}],
        },
    ).json()
    tracked = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W1", "location": "boite 3"}]},
    ).json()

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{tracked['id']}/preuves",
        json={"description": "Mesure", "source": "profilometre"},
    ).json()
    assert client.get(f"/api/projects/{slug}/experiences/{with_evidence['id']}").json()["physical_tracking"] == [
        {"sample_id": "W1", "location": "boite 3"}
    ]
