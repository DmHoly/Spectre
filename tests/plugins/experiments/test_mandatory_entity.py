"""Every experiment must end up traceable to a real physical entity - but the wafers actually
launched are often only known once the FDL is filled in. So naming them is optional at launch (each
place - a campaign variant, a replicate - stays blank, to be associated later from the FDL of the
study) and enforced at conclusion (spectre.plugins.experiments.service.conclude). Evolving inherits
the places the line already carries.
"""

from __future__ import annotations

from support.experiments import evolve, experiment_url, launch, launch_body, post_evolve, post_launch, track_entities
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, steps

BLANK = {"sample_id": None, "location": None}


def _launch_response(client, slug, entities, **fields):
    return post_launch(client, slug, title="Etude", intent="Depart", entities=entities, **fields)


def _evolve_response(client, slug, ref, **fields):
    return post_evolve(client, slug, ref, steps=steps(30), title="Suite", intent="Continuer", **fields)


def _conclude(client, slug, ref):
    return client.put(f"{experiment_url(slug, ref)}/conclusion", json={"status": "concluded", "objective_results": []})


def test_launching_without_an_entity_leaves_one_place_to_associate(client):
    slug = signup_with_microproject(client, "optional-launch@example.com")
    response = _launch_response(client, slug, [])
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [BLANK]


def test_launching_with_planned_wafers_keeps_one_place_per_wafer(client):
    slug = signup_with_microproject(client, "optional-planned@example.com")
    response = _launch_response(client, slug, [{}, {}, {}])
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [BLANK, BLANK, BLANK]


def test_launching_with_an_entity_stores_it_on_the_new_experiment(client):
    slug = signup_with_microproject(client, "mandatory-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "W1", "location": "Tiroir 2"}])
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [{"sample_id": "W1", "location": "Tiroir 2"}]


def test_launching_a_campaign_without_an_entity_gives_one_blank_place_per_variant(client):
    slug = signup_with_microproject(client, "optional-campaign@example.com")
    response = _launch_response(client, slug, [], kind="campaign", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [BLANK, BLANK, BLANK]


def test_launching_a_campaign_pads_the_remaining_variants_blank(client):
    slug = signup_with_microproject(client, "mandatory-campaign-ok@example.com")
    response = _launch_response(client, slug, [{"sample_id": "Ref-1"}], kind="campaign", plan=campaign_plan([10, 20, 30]))
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [{"sample_id": "Ref-1", "location": None}, BLANK, BLANK]


def test_the_fdl_of_the_study_is_recorded_normalized_and_kept_by_an_evolution(client):
    slug = signup_with_microproject(client, "study-fdl@example.com")
    launched = _launch_response(client, slug, [{}, {}], fdl=["1234", "fdl 1234", "abc 7"]).json()
    assert launched["fdl"] == ["FDL-1234", "ABC-7"]
    evolved = _evolve_response(client, slug, launched["id"]).json()
    assert evolved["fdl"] == ["FDL-1234", "ABC-7"]
    assert evolved["physical_tracking"] == [BLANK, BLANK]
    replaced = _evolve_response(client, slug, launched["id"], fdl=[]).json()
    assert replaced["fdl"] == []


def test_the_places_are_associated_later_with_the_wafers_of_the_fdl(client):
    slug = signup_with_microproject(client, "associate@example.com")
    launched = launch(client, slug, entities=[{}, {}])
    assert _conclude(client, slug, launched["id"]).status_code == 422
    # la carte « Plaques » : la FDL de l'étude, puis chaque place associée à une de ses plaques
    response = client.put(
        f"{experiment_url(slug, launched['id'])}/entities",
        json={"fdl": ["5"], "entities": [{"sample_id": "D5-W03", "fdl": ["FDL-5"]}, {"sample_id": None}]},
    )
    assert response.status_code == 200
    assert response.json()["fdl"] == ["FDL-5"]
    assert response.json()["physical_tracking"] == [{"sample_id": "D5-W03", "location": None, "fdl": ["FDL-5"]}, BLANK]
    # sans fdl, celles de l'étude restent
    kept = track_entities(client, slug, launched["id"], [{"sample_id": "D5-W03"}, {"sample_id": "D5-W04"}])
    assert kept["fdl"] == ["FDL-5"]
    assert _conclude(client, slug, launched["id"]).status_code == 200


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


def test_evolving_a_version_without_a_wafer_is_allowed(client):
    slug = signup_with_microproject(client, "optional-evolve@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    track_entities(client, slug, launched["id"], [{}])
    evolved = _evolve_response(client, slug, launched["id"])
    assert evolved.status_code == 201
    assert evolved.json()["physical_tracking"] == [BLANK]


def test_concluding_without_a_tracked_entity_is_rejected(client):
    slug = signup_with_microproject(client, "mandatory-conclude-blocked@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    cleared = track_entities(client, slug, launched["id"], [{}])

    response = _conclude(client, slug, launched["id"])
    assert response.status_code == 422 and response.json()["code"] == "entity_required"
    assert client.get(experiment_url(slug, launched["id"])).json()["version_id"] == cleared["version_id"]  # rien d'écrit


def test_concluding_a_tracked_experiment_still_works(client):
    slug = signup_with_microproject(client, "mandatory-conclude-ok@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W1"}])
    response = _conclude(client, slug, launched["id"])
    assert response.status_code == 200
    assert response.json()["status"] == "concluded"


def test_a_line_from_a_version_names_its_own_wafers(client):
    # une nouvelle piste ne reprend pas en silence les plaques de sa version de départ : elle nomme
    # les siennes - les mêmes, de nouvelles, ou aucune encore (à associer depuis sa FDL)
    slug = signup_with_microproject(client, "mandatory-from-version@example.com")
    launched = launch(client, slug, entities=[{"sample_id": "W9"}], fdl=["FDL-9"])
    body = launch_body(title="Suite", intent="x", entities=[], from_version={"experiment_id": launched["id"]})
    response = client.post(f"/api/microprojects/{slug}/experiments", json=body)
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [BLANK] and response.json()["fdl"] == []
    body = launch_body(title="Suite 2", intent="x", entities=[{"sample_id": "W9"}], from_version={"experiment_id": launched["id"]})
    response = client.post(f"/api/microprojects/{slug}/experiments", json=body)
    assert response.status_code == 201
    assert response.json()["physical_tracking"] == [{"sample_id": "W9", "location": None}]
