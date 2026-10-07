"""Every experiment must be traceable to a real physical entity - enforced at creation
(spectre.plugins.experiments.service.create) and again at conclusion (service.conclude). Evolving
usually just inherits the entity the line already carries, so the rule is transparent for a normal
lineage - it only bites when a version genuinely has none, whether because it predates the rule or
because PUT .../entities blanked it.
"""

from __future__ import annotations

from support.experiments import evolve, experiment_url, launch, launch_body, post_evolve, post_launch, track_entities
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, steps


def _launch_response(client, slug, entities, **fields):
    return post_launch(client, slug, title="Etude", intent="Depart", entities=entities, **fields)


def _evolve_response(client, slug, ref, **fields):
    return post_evolve(client, slug, ref, steps=steps(30), title="Suite", intent="Continuer", **fields)


def test_launching_without_an_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-launch@example.com")
    response = _launch_response(client, slug, [])
    assert response.status_code == 422
    assert response.json()["code"] == "entity_required"


def test_launching_with_only_a_blank_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-blank@example.com")
    assert _launch_response(client, slug, [{"sample_id": "  "}]).status_code == 422


def test_launching_with_an_entity_stores_it_on_the_new_experiment(client):
    slug = signup_with_microproject(client, "mandatory-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "W1", "location": "Tiroir 2"}])
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [{"sample_id": "W1", "location": "Tiroir 2"}]


def test_launching_a_campaign_without_an_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-campaign@example.com")
    response = _launch_response(client, slug, [], kind="campaign", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 422
    assert "campagne" in response.json()["detail"]


def test_launching_a_campaign_pads_the_remaining_variants_blank(client):
    slug = signup_with_microproject(client, "mandatory-campaign-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "Ref-1"}], kind="campaign", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [
        {"sample_id": "Ref-1", "location": None},
        {"sample_id": None, "location": None},
        {"sample_id": None, "location": None},
    ]


def test_evolving_inherits_the_parent_entity_without_needing_to_resupply_it(client):
    slug = signup_with_microproject(client, "mandatory-evolve-inherit@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    evolved = _evolve_response(client, slug, launched["id"])
    assert evolved.status_code == 201
    assert evolved.json()["physical_tracking"] == [{"sample_id": "W1", "location": None}]


def test_evolving_can_override_the_inherited_entity(client):
    slug = signup_with_microproject(client, "mandatory-evolve-override@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    evolved = evolve(
        client, slug, launched["id"], title="Suite", intent="Continuer", steps=steps(30), entities=[{"sample_id": "W2", "location": "Congélateur"}]
    )
    assert evolved["physical_tracking"] == [{"sample_id": "W2", "location": "Congélateur"}]


def test_evolving_a_version_whose_entity_was_cleared_requires_a_new_one(client):
    slug = signup_with_microproject(client, "mandatory-evolve-blocked@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    # PUT .../entities accepts a blank entry (e.g. a sample lost or discarded) - this is the only
    # way to legitimately land back in the "no tracked entity" state once the rule is otherwise
    # enforced at every creation point.
    track_entities(client, slug, launched["id"], [{}])

    assert _evolve_response(client, slug, launched["id"]).status_code == 422
    assert _evolve_response(client, slug, launched["id"], entities=[{"sample_id": "W1-bis"}]).status_code == 201


def test_concluding_without_a_tracked_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-conclude-blocked@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    cleared = track_entities(client, slug, launched["id"], [{}])

    response = client.put(f"{experiment_url(slug, launched['id'])}/conclusion", json={"status": "concluded", "objective_results": []})
    assert response.status_code == 422
    assert client.get(experiment_url(slug, launched["id"])).json()["version_id"] == cleared["version_id"]  # rien d'écrit


def test_concluding_a_tracked_experiment_still_works(client):
    slug = signup_with_microproject(client, "mandatory-conclude-ok@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    response = client.put(f"{experiment_url(slug, launched['id'])}/conclusion", json={"status": "concluded", "objective_results": []})
    assert response.status_code == 200
    assert response.json()["status"] == "concluded"


def test_a_line_from_a_version_names_its_own_wafers(client):
    # une nouvelle piste ne reprend pas en silence les plaques de sa version de départ : elle nomme
    # les siennes - les mêmes, ou de nouvelles
    slug = signup_with_microproject(client, "mandatory-from-version@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W9"}])
    body = launch_body(title="Suite", intent="x", entities=[], from_version={"experiment_id": launched["id"]})
    response = client.post(f"/api/microprojects/{slug}/experiments", json=body)
    assert response.status_code == 422 and response.json()["code"] == "entity_required"
    body = launch_body(title="Suite", intent="x", entities=[{"sample_id": "W9"}], from_version={"experiment_id": launched["id"]})
    response = client.post(f"/api/microprojects/{slug}/experiments", json=body)
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [{"sample_id": "W9", "location": None}]
