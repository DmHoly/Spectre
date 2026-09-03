from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": thickness, "unit": "nm"},
        }
    ]


def test_fork_creates_a_new_branch_and_is_visible_as_a_child(client):
    client.post("/api/auth/register", json={"email": "fork@example.com", "password": "supersecret", "name": "F"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]

    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(20),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    assert launched["branch"] == "reference"

    # continue the same branch
    continued = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(15), "title": "Reference", "intent": "Reduire un peu"},
    ).json()
    assert continued["branch"] == "reference"

    # fork off a new branch from the same starting point
    forked = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Piste epaisse",
            "intent": "Explorer une epaisseur plus grande",
            "new_branch": "piste-epaisse",
        },
    ).json()
    assert forked["branch"] == "piste-epaisse"
    assert forked["id"] != continued["id"]

    parent_detail = client.get(f"/api/projects/{slug}/experiences/{launched['id']}").json()
    child_ids = {c["id"] for c in parent_detail["children"]}
    assert child_ids == {continued["id"], forked["id"]}

    # the two forks are independent branches, both rooted at the same parent
    assert client.get(f"/api/projects/{slug}/experiences/{continued['id']}").json()["parents"] == [launched["id"]]
    assert client.get(f"/api/projects/{slug}/experiences/{forked['id']}").json()["parents"] == [launched["id"]]


def test_forking_onto_an_existing_branch_name_from_elsewhere_is_rejected(client):
    client.post("/api/auth/register", json={"email": "fork2@example.com", "password": "supersecret", "name": "F2"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    other = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Autre depart",
            "intent": "Depart 2",
            "entities": [{"sample_id": "W2"}],
        },
    ).json()

    client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(25),
            "title": "Piste",
            "intent": "Explorer",
            "new_branch": "piste-partagee",
        },
    )
    # "piste-partagee" already exists and its tip isn't among this commit's parents
    response = client.post(
        f"/api/projects/{slug}/experiences/{other['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(35),
            "title": "Collision",
            "intent": "Y",
            "new_branch": "piste-partagee",
        },
    )
    assert response.status_code == 400


def test_continuing_from_a_version_that_is_no_longer_the_tip_does_not_crash(client):
    # regression: "continuer cette piste" (no new_branch) from an experience someone already
    # evolved past used to hit Follow's raw branch-collision error - a 400 with English git
    # vocabulary in the message. It should instead silently succeed on a fresh branch.
    client.post("/api/auth/register", json={"email": "stale@example.com", "password": "supersecret", "name": "S"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(15), "title": "Reference v2", "intent": "Suite"},
    )

    # launched['id'] is no longer its branch's tip - continuing from it anyway must still work
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Autre suite", "intent": "Depuis le depart"},
    )
    assert response.status_code == 201
    assert response.json()["id"] != launched["id"]


def test_concluding_a_version_that_is_no_longer_the_tip_does_not_crash(client):
    client.post("/api/auth/register", json={"email": "stale2@example.com", "password": "supersecret", "name": "S2"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Reference",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(15), "title": "Reference v2", "intent": "Suite"},
    )

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/conclure",
        json={"status": "concluded", "summary": "Conclu malgre tout", "objective_results": []},
    )
    assert response.status_code == 201

    evidence_response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Mesure ajoutee apres coup", "source": "profilometre"},
    )
    assert evidence_response.status_code == 201
