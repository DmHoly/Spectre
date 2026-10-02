"""Refs (spectre.plugins.experiments.refs): tagging an experience as a named, reusable starting point - built on
Follow's own tag (an immutable pointer to one experiment), with a default "ref vX.Y.Z" name from
spectre.plugins.experiments.versioning when no nickname is given. See test_atlas.py for the same
condensed-edges algorithm applied to branch tips instead of refs.
"""

from __future__ import annotations

from support.experiments import conclude, create_ref, evolve, get_experience, launch, launch_campaign, tag
from support.microprojects import signup_with_microproject
from support.structures import campaign_plan, etch, steps, substrate


def _launch_reference(client, slug, title="Reference", thickness=20):
    return launch(client, slug, title=title, intent="Depart", steps=steps(thickness))


def test_default_ref_name_uses_the_computed_version(client):
    slug = signup_with_microproject(client, "refs-default@example.com")
    launched = _launch_reference(client, slug)

    response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/ref", json={})
    assert response.status_code == 201
    assert response.json() == {"name": "ref v1.0.0", "experiment_id": launched["id"]}

    assert get_experience(client, slug, launched["id"])["ref_names"] == ["ref v1.0.0"]


def test_ref_can_be_given_a_nickname(client):
    slug = signup_with_microproject(client, "refs-nickname@example.com")
    launched = _launch_reference(client, slug)

    response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/ref", json={"name": "  omega  "})
    assert response.status_code == 201
    assert response.json() == {"name": "omega", "experiment_id": launched["id"]}


def test_a_nickname_with_a_slash_is_refused(client):
    # a ref is addressed as a single {ref} path segment - "a/b" could never be reached again
    slug = signup_with_microproject(client, "refs-slash@example.com")
    launched = _launch_reference(client, slug)

    response = client.post(f"/api/microprojets/{slug}/experiences/{launched['id']}/ref", json={"name": "omega/2"})
    assert response.status_code == 422
    assert "/" in response.json()["detail"]
    assert get_experience(client, slug, launched["id"])["ref_names"] == ["ref v1.0.0"]  # only the automatic one


def test_a_nickname_already_used_elsewhere_conflicts(client):
    slug = signup_with_microproject(client, "refs-conflict@example.com")
    a = _launch_reference(client, slug, title="A")
    b = _launch_reference(client, slug, title="B")  # a distinct branch (different title slugifies differently)

    create_ref(client, slug, a["id"], "omega")
    response = client.post(f"/api/microprojets/{slug}/experiences/{b['id']}/ref", json={"name": "omega"})
    assert response.status_code == 409


def test_tagging_the_same_experience_with_no_nickname_twice_is_idempotent(client):
    slug = signup_with_microproject(client, "refs-idempotent@example.com")
    launched = _launch_reference(client, slug)

    first = create_ref(client, slug, launched["id"])
    second = create_ref(client, slug, launched["id"])
    assert first == second == {"name": "ref v1.0.0", "experiment_id": launched["id"]}


def test_evolving_from_a_ref_name_works_like_any_other_ref(client):
    slug = signup_with_microproject(client, "refs-evolve@example.com")
    launched = _launch_reference(client, slug)
    create_ref(client, slug, launched["id"], "omega")

    response = client.post(
        f"/api/microprojets/{slug}/experiences/omega/evoluer",
        json={"substrate": substrate(), "steps": steps(40), "title": "Suite", "intent": "Depuis omega"},
    )
    assert response.status_code == 201
    assert response.json()["id"] != launched["id"]

    # a ref name with a space (the default "ref vX.Y.Z") is just as good, encoded in the path
    assert get_experience(client, slug, "ref%20v1.0.0")["id"] == launched["id"]


def test_the_microprojects_first_experience_becomes_a_ref_automatically(client):
    slug = signup_with_microproject(client, "refs-auto-first@example.com")
    launched = _launch_reference(client, slug)

    items = client.get(f"/api/microprojets/{slug}/refs").json()["items"]
    assert len(items) == 1
    assert items[0]["experiment_id"] == launched["id"]
    assert items[0]["names"] == ["ref v1.0.0"]

    # a later experience in the same microproject does *not* also get auto-tagged
    second = launch(client, slug, title="Autre depart", intent="Depart 2", steps=steps(30), entities=[{"sample_id": "W2"}])
    items = client.get(f"/api/microprojets/{slug}/refs").json()["items"]
    assert {i["experiment_id"] for i in items} == {launched["id"]}
    assert second["id"] != launched["id"]


def test_the_microprojects_first_campaign_becomes_a_ref_automatically(client):
    slug = signup_with_microproject(client, "refs-auto-first-campaign@example.com")
    campaign = launch_campaign(client, slug, campaign_plan([10, 20]), entities=[{"sample_id": "V0"}])

    items = client.get(f"/api/microprojets/{slug}/refs").json()["items"]
    assert len(items) == 1
    assert items[0]["experiment_id"] == campaign["id"]


def test_refs_list_and_graph_condense_intermediate_versions(client):
    slug = signup_with_microproject(client, "refs-graph@example.com")
    root = _launch_reference(client, slug, thickness=10)
    create_ref(client, slug, root["id"], "omega")

    # a lightweight evolution that doesn't change the process at all - version stays 1.0.0,
    # collapsed out of the ref graph the same way an unchanged commit is collapsed out of the
    # microproject's own version graph (spectre.plugins.experiments.versioning.determine_keep_ids).
    tagged = tag(client, slug, root["id"], ["a-suivre"])

    # a real structural change (a step added) - bumps to 2.0.0
    grown = evolve(client, slug, tagged["id"], title="Suite", intent="Ajout d'une gravure", steps=steps(10) + [etch(depth_nm=5)])
    create_ref(client, slug, grown["id"], "banane")

    items = client.get(f"/api/microprojets/{slug}/refs").json()["items"]
    version_by_name = {entry["names"][0]: entry["version"] for entry in items}
    assert version_by_name == {"omega": "1.0.0", "banane": "2.0.0"}

    graph = client.get(f"/api/microprojets/{slug}/refs/graphe").json()
    edges = {(e["from"], e["to"]) for e in graph["edges"]}
    # the ordinary commit ("tagged") in between is collapsed out - one edge straight from ref to ref
    assert edges == {(root["id"], grown["id"])}


def test_ref_list_exposes_the_conclusion_decision(client):
    slug = signup_with_microproject(client, "refs-decision@example.com")
    launched = _launch_reference(client, slug)
    concluded = conclude(client, slug, launched["id"], decision="inconclusive")
    create_ref(client, slug, concluded["id"], "essai-a")

    items = client.get(f"/api/microprojets/{slug}/refs").json()["items"]
    assert items[0]["decision"] == "inconclusive"  # for the "Non concluante" badge nuance
