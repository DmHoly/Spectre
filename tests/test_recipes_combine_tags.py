from __future__ import annotations

from support.experiments import add_evidence, conclude, get_experience, launch, launch_campaign, tag
from support.microprojects import signup_with_microproject
from support.structures import steps


def test_combine_two_experiences_keeps_the_base_structure_and_links_the_other(client):
    slug = signup_with_microproject(client, "combine@example.com")
    a = launch(client, slug, title="Piste A", intent="Depart A", steps=steps(20))
    b = launch(client, slug, title="Piste B", intent="Depart B", steps=steps(40), entities=[{"sample_id": "W2"}])

    combined = client.post(
        f"/api/microprojets/{slug}/experiences/{a['id']}/combiner",
        json={"other_id": b["id"], "title": "Synthese A+B", "intent": "Regrouper les deux pistes"},
    )
    assert combined.status_code == 201
    combined_id = combined.json()["id"]

    detail = get_experience(client, slug, combined_id)
    assert sorted(detail["parents"]) == sorted([a["id"], b["id"]])
    assert detail["title"] == "Synthese A+B"
    # kept A's structure/steps (the default, conflict-free behaviour)
    process = client.get(f"/api/microprojets/{slug}/experiences/{combined_id}/process").json()
    assert process["steps"][0]["thickness"]["value"] == 20


def test_combine_rejects_combining_an_experience_with_itself(client):
    slug = signup_with_microproject(client, "combineself@example.com")
    a = launch(client, slug, title="Solo", intent="Depart")
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{a['id']}/combiner",
        json={"other_id": a["id"], "title": "X", "intent": "Y"},
    )
    assert response.status_code == 422


def test_combine_rejects_a_single_experience_with_a_campaign(client):
    slug = signup_with_microproject(client, "combinetypes@example.com")
    single = launch(client, slug, title="Solo", intent="Depart")
    campaign = launch_campaign(client, slug, intent="Balayage", entities=[{"sample_id": "placeholder"}])
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{single['id']}/combiner",
        json={"other_id": campaign["id"], "title": "X", "intent": "Y"},
    )
    assert response.status_code == 422


def test_setting_and_removing_tags_records_a_new_version_and_preserves_status(client):
    slug = signup_with_microproject(client, "tags@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")

    tagged = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/etiquettes",
        json={"tags": ["a valider", "prioritaire", "a valider"]},
    )
    assert tagged.status_code == 201
    assert tagged.json()["tags"] == ["a valider", "prioritaire"]
    tagged_id = tagged.json()["id"]
    assert tagged_id != launched["id"]

    detail = get_experience(client, slug, tagged_id)
    assert detail["tags"] == ["a valider", "prioritaire"]
    assert detail["status"] == "draft"  # tagging must not change the status

    assert tag(client, slug, tagged_id, ["prioritaire"])["tags"] == ["prioritaire"]


def test_adding_evidence_or_concluding_preserves_existing_tags(client):
    slug = signup_with_microproject(client, "tagscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    tagged = tag(client, slug, launched["id"], ["important"])

    with_evidence = add_evidence(client, slug, tagged["id"], source="profilometre")
    assert get_experience(client, slug, with_evidence["id"])["tags"] == ["important"]

    concluded = conclude(client, slug, with_evidence["id"], summary="Fini", objective_results=[])
    detail = get_experience(client, slug, concluded["id"])
    assert detail["tags"] == ["important"]
    assert detail["status"] == "concluded"


def test_concluding_does_not_reset_status_of_a_later_evidence_addition(client):
    # regression: add_evidence used to leave `conclusion` at its fresh default, silently
    # un-concluding an already-concluded experience the moment evidence was attached to it.
    slug = signup_with_microproject(client, "statuscarry@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    concluded = conclude(client, slug, launched["id"], summary="Fini", objective_results=[])
    assert get_experience(client, slug, concluded["id"])["status"] == "concluded"

    with_evidence = add_evidence(client, slug, concluded["id"], "Mesure tardive", source="profilometre")
    assert get_experience(client, slug, with_evidence["id"])["status"] == "concluded"
