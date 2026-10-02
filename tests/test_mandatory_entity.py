"""Every experience must be traceable to a real physical entity - enforced at creation
(spectre.api.structures::launch_experience/launch_campaign) and again at conclusion
(spectre.api.experiments::conclude_experience). Evolving usually just inherits the entity the
parent already carries (spectre.core.structures::has_tracked_physical_entity /
clean_entity_entries), so the rule is transparent for a normal lineage - it only bites when a
version genuinely has none, whether because it predates the rule or because /entites blanked it.
"""

from __future__ import annotations

from support.experiments import evolve, get_experience, launch, launch_body, track_entities
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, steps, substrate


def _launch_response(client, slug, entities, path="experiences", **fields):
    body = launch_body(title="Etude", intent="Depart", entities=entities, **fields)
    return client.post(f"/api/microprojets/{slug}/{path}", json=body)


def _evolve_response(client, slug, ref, **fields):
    body = {"substrate": substrate(), "steps": steps(30), "title": "Suite", "intent": "Continuer", **fields}
    return client.post(f"/api/microprojets/{slug}/experiences/{ref}/evoluer", json=body)


def test_launching_without_an_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-launch@example.com")
    assert _launch_response(client, slug, []).status_code == 422


def test_launching_with_only_a_blank_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-blank@example.com")
    assert _launch_response(client, slug, [{"sample_id": "  "}]).status_code == 422


def test_launching_with_an_entity_stores_it_on_the_new_experiment(client):
    slug = signup_with_microproject(client, "mandatory-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "W1", "location": "Tiroir 2"}])
    assert response.status_code == 201
    detail = get_experience(client, slug, response.json()["id"])
    assert detail["physical_tracking"] == [{"sample_id": "W1", "location": "Tiroir 2"}]


def test_launching_a_campaign_without_an_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-campaign@example.com")
    response = _launch_response(client, slug, [], path="experiences/campagne", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 422


def test_launching_a_campaign_pads_the_remaining_variants_blank(client):
    slug = signup_with_microproject(client, "mandatory-campaign-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "Ref-1"}], path="experiences/campagne", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 201
    detail = get_experience(client, slug, response.json()["id"])
    assert detail["physical_tracking"] == [{"sample_id": "Ref-1", "location": None}, {"sample_id": None, "location": None}, {"sample_id": None, "location": None}]


def test_evolving_inherits_the_parent_entity_without_needing_to_resupply_it(client):
    slug = signup_with_microproject(client, "mandatory-evolve-inherit@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    evolved = _evolve_response(client, slug, launched["id"])
    assert evolved.status_code == 201
    detail = get_experience(client, slug, evolved.json()["id"])
    assert detail["physical_tracking"] == [{"sample_id": "W1", "location": None}]


def test_evolving_can_override_the_inherited_entity(client):
    slug = signup_with_microproject(client, "mandatory-evolve-override@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    evolved = evolve(client, slug, launched["id"], title="Suite", intent="Continuer", steps=steps(30), entities=[{"sample_id": "W2", "location": "Congélateur"}])
    detail = get_experience(client, slug, evolved["id"])
    assert detail["physical_tracking"] == [{"sample_id": "W2", "location": "Congélateur"}]


def test_evolving_a_version_whose_entity_was_cleared_requires_a_new_one(client):
    slug = signup_with_microproject(client, "mandatory-evolve-blocked@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    # /entites accepts a blank entry (e.g. a sample lost or discarded) - this is the only way to
    # legitimately land back in the "no tracked entity" state once the rule is otherwise enforced
    # at every creation point.
    cleared = track_entities(client, slug, launched["id"], [{}])

    assert _evolve_response(client, slug, cleared["id"]).status_code == 422
    assert _evolve_response(client, slug, cleared["id"], entities=[{"sample_id": "W1-bis"}]).status_code == 201


def test_concluding_without_a_tracked_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-conclude-blocked@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    cleared = track_entities(client, slug, launched["id"], [{}])

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{cleared['id']}/conclure",
        json={"status": "concluded", "objective_results": []},
    )
    assert response.status_code == 422


def test_concluding_a_tracked_experience_still_works(client):
    slug = signup_with_microproject(client, "mandatory-conclude-ok@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/conclure",
        json={"status": "concluded", "objective_results": []},
    )
    assert response.status_code == 201
