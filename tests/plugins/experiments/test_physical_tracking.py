from __future__ import annotations

from support.experiments import experiment_url, get_experiment, launch, launch_campaign, track_entities, variants
from support.microprojects import signup_with_microproject
from support.notebook import add_manual


def _launch_placeholder(client, slug):
    return launch(client, slug, title="Reference", intent="Depart", entities=[{"sample_id": "placeholder"}])


def test_setting_physical_tracking_on_a_single_experiment(client):
    slug = signup_with_microproject(client, "physical@example.com")
    launched = _launch_placeholder(client, slug)

    response = client.put(f"{experiment_url(slug, launched['id'])}/entities", json={"entities": [{"sample_id": "W12-A3", "location": "congelateur B"}]})
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == launched["id"]
    assert detail["version_id"] != launched["version_id"]
    assert detail["physical_tracking"] == [{"sample_id": "W12-A3", "location": "congelateur B"}]
    assert detail["status"] == "draft"  # bookkeeping only, doesn't touch status


def test_physical_tracking_of_a_single_experiment_takes_replicates_but_not_none(client):
    slug = signup_with_microproject(client, "physicalcount@example.com")
    launched = _launch_placeholder(client, slug)
    replicates = track_entities(client, slug, launched["id"], [{"sample_id": "A"}, {"sample_id": "B"}])
    assert [e["sample_id"] for e in replicates["physical_tracking"]] == ["A", "B"]
    response = client.put(f"{experiment_url(slug, launched['id'])}/entities", json={"entities": []})
    assert response.status_code == 422
    assert response.json()["code"] == "entity_count"


def test_physical_tracking_on_a_campaign_matches_entity_count(client):
    slug = signup_with_microproject(client, "physicalcampaign@example.com")
    campaign = launch_campaign(client, slug, intent="Balayage", entities=[{"sample_id": "placeholder"}])

    too_few = client.put(f"{experiment_url(slug, campaign['id'])}/entities", json={"entities": [{"sample_id": "A"}]})
    assert too_few.status_code == 422

    track_entities(client, slug, campaign["id"], [{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}])
    assert [e["sample_id"] for e in variants(client, slug, campaign["id"])["physical_tracking"]] == ["A", "B", "C"]


def test_physical_tracking_carries_forward_through_the_notebook_and_conclude(client):
    slug = signup_with_microproject(client, "physicalcarry@example.com")
    launched = _launch_placeholder(client, slug)
    track_entities(client, slug, launched["id"], [{"sample_id": "W1", "location": "boite 3"}])

    add_manual(client, slug, launched["id"], measurements=[{"text": "profilometre"}])
    assert get_experiment(client, slug, launched["id"])["physical_tracking"] == [{"sample_id": "W1", "location": "boite 3"}]
