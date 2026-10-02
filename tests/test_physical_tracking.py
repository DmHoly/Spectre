from __future__ import annotations

from support.experiments import add_evidence, get_experience, launch, launch_campaign, track_entities
from support.microprojects import signup_with_microproject


def _launch_placeholder(client, slug):
    return launch(client, slug, title="Reference", intent="Depart", entities=[{"sample_id": "placeholder"}])


def test_setting_physical_tracking_on_a_single_experience(client):
    slug = signup_with_microproject(client, "physical@example.com")
    launched = _launch_placeholder(client, slug)

    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "W12-A3", "location": "congelateur B"}]},
    )
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert new_id != launched["id"]

    detail = get_experience(client, slug, new_id)
    assert detail["physical_tracking"] == [{"sample_id": "W12-A3", "location": "congelateur B"}]
    assert detail["status"] == "draft"  # bookkeeping only, doesn't touch status


def test_physical_tracking_rejects_wrong_entity_count_for_a_single_experience(client):
    slug = signup_with_microproject(client, "physicalcount@example.com")
    launched = _launch_placeholder(client, slug)
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/entites",
        json={"entities": [{"sample_id": "A"}, {"sample_id": "B"}]},
    )
    assert response.status_code == 422


def test_physical_tracking_on_a_campaign_matches_entity_count(client):
    slug = signup_with_microproject(client, "physicalcampaign@example.com")
    campaign = launch_campaign(client, slug, intent="Balayage", entities=[{"sample_id": "placeholder"}])

    too_few = client.post(
        f"/api/microprojets/{slug}/experiences/{campaign['id']}/entites",
        json={"entities": [{"sample_id": "A"}]},
    )
    assert too_few.status_code == 422

    ok = client.post(
        f"/api/microprojets/{slug}/experiences/{campaign['id']}/entites",
        json={"entities": [{"sample_id": "A"}, {"sample_id": "B"}, {"sample_id": "C"}]},
    )
    assert ok.status_code == 201

    matrix = client.get(f"/api/microprojets/{slug}/experiences/{ok.json()['id']}/matrice").json()
    assert [e["sample_id"] for e in matrix["physical_tracking"]] == ["A", "B", "C"]


def test_physical_tracking_carries_forward_through_evidence_and_conclude(client):
    slug = signup_with_microproject(client, "physicalcarry@example.com")
    launched = _launch_placeholder(client, slug)
    tracked = track_entities(client, slug, launched["id"], [{"sample_id": "W1", "location": "boite 3"}])

    with_evidence = add_evidence(client, slug, tracked["id"], source="profilometre")
    assert get_experience(client, slug, with_evidence["id"])["physical_tracking"] == [{"sample_id": "W1", "location": "boite 3"}]
