"""Every experience must be traceable to a real physical entity - enforced at creation
(spectre.api.structures::launch_experience/launch_campaign) and again at conclusion
(spectre.api.experiments::conclude_experience). Evolving usually just inherits the entity the
parent already carries (spectre.core.structures::has_tracked_physical_entity /
clean_entity_entries), so the rule is transparent for a normal lineage - it only bites when a
version genuinely has none, whether because it predates the rule or because /entites blanked it.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_project(client, email):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": "Projet"}).json()["slug"]


def _launch_body(entities=None, **overrides):
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Etude",
        "intent": "Depart",
        "entities": entities if entities is not None else [{"sample_id": "W1"}],
    }
    body.update(overrides)
    return body


def test_launching_without_an_entity_is_rejected(client):
    slug = _register_and_project(client, "mandatory-launch@example.com")
    response = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[]))
    assert response.status_code == 422


def test_launching_with_only_a_blank_entity_is_rejected(client):
    slug = _register_and_project(client, "mandatory-blank@example.com")
    response = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "  "}]))
    assert response.status_code == 422


def test_launching_with_an_entity_stores_it_on_the_new_experiment(client):
    slug = _register_and_project(client, "mandatory-ok@example.com")
    response = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1", "location": "Tiroir 2"}]))
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{response.json()['id']}").json()
    assert detail["physical_tracking"] == [{"sample_id": "W1", "location": "Tiroir 2"}]


def test_launching_a_campaign_without_an_entity_is_rejected(client):
    slug = _register_and_project(client, "mandatory-campaign@example.com")
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]},
        "title": "Campagne",
        "intent": "Balayer",
        "entities": [],
    }
    response = client.post(f"/api/projects/{slug}/experiences/campagne", json=body)
    assert response.status_code == 422


def test_launching_a_campaign_pads_the_remaining_variants_blank(client):
    slug = _register_and_project(client, "mandatory-campaign-ok@example.com")
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "plan": {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]},
        "title": "Campagne",
        "intent": "Balayer",
        "entities": [{"sample_id": "Ref-1"}],
    }
    response = client.post(f"/api/projects/{slug}/experiences/campagne", json=body)
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{response.json()['id']}").json()
    assert detail["physical_tracking"] == [{"sample_id": "Ref-1", "location": None}, {"sample_id": None, "location": None}, {"sample_id": None, "location": None}]


def test_evolving_inherits_the_parent_entity_without_needing_to_resupply_it(client):
    slug = _register_and_project(client, "mandatory-evolve-inherit@example.com")
    launched = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1"}])).json()
    evolved = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(30), "title": "Suite", "intent": "Continuer"},
    )
    assert evolved.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{evolved.json()['id']}").json()
    assert detail["physical_tracking"] == [{"sample_id": "W1", "location": None}]


def test_evolving_can_override_the_inherited_entity(client):
    slug = _register_and_project(client, "mandatory-evolve-override@example.com")
    launched = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1"}])).json()
    evolved = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Suite",
            "intent": "Continuer",
            "entities": [{"sample_id": "W2", "location": "Congélateur"}],
        },
    )
    assert evolved.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{evolved.json()['id']}").json()
    assert detail["physical_tracking"] == [{"sample_id": "W2", "location": "Congélateur"}]


def test_evolving_a_version_whose_entity_was_cleared_requires_a_new_one(client):
    slug = _register_and_project(client, "mandatory-evolve-blocked@example.com")
    launched = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1"}])).json()
    # /entites accepts a blank entry (e.g. a sample lost or discarded) - this is the only way to
    # legitimately land back in the "no tracked entity" state once the rule is otherwise enforced
    # at every creation point.
    cleared = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/entites", json={"entities": [{}]}).json()

    blocked = client.post(
        f"/api/projects/{slug}/experiences/{cleared['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(30), "title": "Suite", "intent": "Continuer"},
    )
    assert blocked.status_code == 422

    fixed = client.post(
        f"/api/projects/{slug}/experiences/{cleared['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Suite",
            "intent": "Continuer",
            "entities": [{"sample_id": "W1-bis"}],
        },
    )
    assert fixed.status_code == 201


def test_concluding_without_a_tracked_entity_is_rejected(client):
    slug = _register_and_project(client, "mandatory-conclude-blocked@example.com")
    launched = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1"}])).json()
    cleared = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/entites", json={"entities": [{}]}).json()

    response = client.post(
        f"/api/projects/{slug}/experiences/{cleared['id']}/conclure",
        json={"status": "concluded", "objective_results": []},
    )
    assert response.status_code == 422


def test_concluding_a_tracked_experience_still_works(client):
    slug = _register_and_project(client, "mandatory-conclude-ok@example.com")
    launched = client.post(f"/api/projects/{slug}/experiences", json=_launch_body(entities=[{"sample_id": "W1"}])).json()
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/conclure",
        json={"status": "concluded", "objective_results": []},
    )
    assert response.status_code == 201
