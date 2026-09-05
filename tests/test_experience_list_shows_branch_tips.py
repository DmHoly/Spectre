"""list_experiences()/project counts show one card per branch (its current tip), not every
version ever committed to it - conclure/preuves/etiquettes each record a new version (experiments
are immutable), so without this a single study kept showing up multiple times, drafts included,
even once concluded.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def test_evidence_then_conclusion_only_shows_the_final_version_once(client):
    slug = _register_and_project(client, "tips-a@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Mesure", "source": "labo"},
    ).json()
    concluded = client.post(
        f"/api/projects/{slug}/experiences/{with_evidence['id']}/conclure", json={"status": "concluded"}
    ).json()

    listed = client.get(f"/api/projects/{slug}/experiences?status=all&limit=50").json()
    matching = [item for item in listed["items"] if item["title"] == "Etude"]
    assert len(matching) == 1
    assert matching[0]["id"] == concluded["id"]
    assert matching[0]["status"] == "concluded"

    # and it must not also appear under "running" - only its (now superseded) drafts were ever running
    running = client.get(f"/api/projects/{slug}/experiences?status=running&limit=50").json()
    assert launched["id"] not in [item["id"] for item in running["items"]]
    assert with_evidence["id"] not in [item["id"] for item in running["items"]]


def test_project_counts_reflect_one_status_per_branch(client):
    slug = _register_and_project(client, "tips-b@example.com")
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Etude",
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves", json={"description": "Mesure", "source": "labo"}
    ).json()
    client.post(f"/api/projects/{slug}/experiences/{with_evidence['id']}/conclure", json={"status": "concluded"})

    payload = client.get(f"/api/projects/{slug}").json()
    assert payload["running_count"] == 0
    assert payload["concluded_count"] == 1


def test_a_fork_still_shows_both_branches_once_each(client):
    slug = _register_and_project(client, "tips-c@example.com")
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
    continued = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(15), "title": "Reference", "intent": "Suite"},
    ).json()
    forked = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(30),
            "title": "Piste epaisse",
            "intent": "Variante",
            "new_branch": "piste-epaisse",
        },
    ).json()

    listed = client.get(f"/api/projects/{slug}/experiences?status=all&limit=50").json()
    ids = {item["id"] for item in listed["items"]}
    assert continued["id"] in ids
    assert forked["id"] in ids
    assert launched["id"] not in ids  # superseded by "continued" on the same branch
