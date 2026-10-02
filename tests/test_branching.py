from __future__ import annotations

from support.experiments import add_evidence, conclude, evolve, get_experience, launch
from support.microprojects import signup_with_microproject
from support.structures import steps, substrate


def test_fork_creates_a_new_branch_and_is_visible_as_a_child(client):
    slug = signup_with_microproject(client, "fork@example.com", name="F")

    launched = launch(client, slug, title="Reference", intent="Depart", steps=steps(20))
    assert launched["branch"] == "reference"

    # continue the same branch
    continued = evolve(client, slug, launched["id"], title="Reference", intent="Reduire un peu", steps=steps(15))
    assert continued["branch"] == "reference"

    # fork off a new branch from the same starting point
    forked = evolve(
        client,
        slug,
        launched["id"],
        title="Piste epaisse",
        intent="Explorer une epaisseur plus grande",
        steps=steps(30),
        new_branch="piste-epaisse",
    )
    assert forked["branch"] == "piste-epaisse"
    assert forked["id"] != continued["id"]

    parent_detail = get_experience(client, slug, launched["id"])
    child_ids = {c["id"] for c in parent_detail["children"]}
    assert child_ids == {continued["id"], forked["id"]}

    # the two forks are independent branches, both rooted at the same parent
    assert get_experience(client, slug, continued["id"])["parents"] == [launched["id"]]
    assert get_experience(client, slug, forked["id"])["parents"] == [launched["id"]]


def test_forking_onto_an_existing_branch_name_from_elsewhere_is_rejected(client):
    slug = signup_with_microproject(client, "fork2@example.com", name="F2")
    launched = launch(client, slug, title="Reference", intent="Depart")
    other = launch(client, slug, title="Autre depart", intent="Depart 2", steps=steps(30), entities=[{"sample_id": "W2"}])

    evolve(client, slug, launched["id"], title="Piste", intent="Explorer", steps=steps(25), new_branch="piste-partagee")
    # "piste-partagee" already exists and its tip isn't among this commit's parents
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{other['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(35), "title": "Collision", "intent": "Y", "new_branch": "piste-partagee"},
    )
    assert response.status_code == 400


def test_a_piste_name_with_a_slash_is_refused(client):
    # every experience route takes a single {ref} path segment: a branch named "a/b" could never
    # be reached again
    slug = signup_with_microproject(client, "fork-slash@example.com")
    launched = launch(client, slug, title="Reference", intent="Depart")
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(35), "title": "Suite", "intent": "Y", "new_branch": "piste/bis"},
    )
    assert response.status_code == 422
    assert "/" in response.json()["detail"]


def test_continuing_from_a_version_that_is_no_longer_the_tip_does_not_crash(client):
    # regression: "continuer cette piste" (no new_branch) from an experience someone already
    # evolved past used to hit Follow's raw branch-collision error - a 400 with English git
    # vocabulary in the message. It should instead silently succeed on a fresh branch.
    slug = signup_with_microproject(client, "stale@example.com", name="S")
    launched = launch(client, slug, title="Reference", intent="Depart")
    evolve(client, slug, launched["id"], title="Reference v2", intent="Suite", steps=steps(15))

    # launched['id'] is no longer its branch's tip - continuing from it anyway must still work
    response = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": substrate(), "steps": steps(40), "title": "Autre suite", "intent": "Depuis le depart"},
    )
    assert response.status_code == 201
    assert response.json()["id"] != launched["id"]


def test_concluding_a_version_that_is_no_longer_the_tip_does_not_crash(client):
    slug = signup_with_microproject(client, "stale2@example.com", name="S2")
    launched = launch(client, slug, title="Reference", intent="Depart")
    evolve(client, slug, launched["id"], title="Reference v2", intent="Suite", steps=steps(15))

    conclude(client, slug, launched["id"], summary="Conclu malgre tout", objective_results=[])
    add_evidence(client, slug, launched["id"], "Mesure ajoutee apres coup", source="profilometre")
