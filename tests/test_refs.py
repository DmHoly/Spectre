"""Refs (spectre.core.refs): tagging an experience as a named, reusable starting point - built on
Follow's own tag (an immutable pointer to one experiment), with a default "ref vX.Y.Z" name from
spectre.core.versioning when no nickname is given. See test_atlas.py for the same
condensed-edges algorithm applied to branch tips instead of refs.
"""

from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {"kind": "deposition", "name": "Oxyde", "material": "SiO2", "recipe": "CVD Conformal", "thickness": {"value": thickness, "unit": "nm"}}
    ]


def _register_and_project(client, email, project_name="Projet"):
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": "T"})
    return client.post("/api/projects", json={"name": project_name}).json()["slug"]


def _launch(client, slug, title="Reference", thickness=20):
    return client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(thickness),
            "title": title,
            "intent": "Depart",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()


def test_default_ref_name_uses_the_computed_version(client):
    slug = _register_and_project(client, "refs-default@example.com")
    launched = _launch(client, slug)

    response = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/ref", json={})
    assert response.status_code == 201
    assert response.json() == {"name": "ref v1.0.0", "experiment_id": launched["id"]}

    detail = client.get(f"/api/projects/{slug}/experiences/{launched['id']}").json()
    assert detail["ref_names"] == ["ref v1.0.0"]


def test_ref_can_be_given_a_nickname(client):
    slug = _register_and_project(client, "refs-nickname@example.com")
    launched = _launch(client, slug)

    response = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/ref", json={"name": "  omega  "})
    assert response.status_code == 201
    assert response.json() == {"name": "omega", "experiment_id": launched["id"]}


def test_a_nickname_already_used_elsewhere_conflicts(client):
    slug = _register_and_project(client, "refs-conflict@example.com")
    a = _launch(client, slug, title="A")
    b = _launch(client, slug, title="B")  # a distinct branch (different title slugifies differently)

    client.post(f"/api/projects/{slug}/experiences/{a['id']}/ref", json={"name": "omega"})
    response = client.post(f"/api/projects/{slug}/experiences/{b['id']}/ref", json={"name": "omega"})
    assert response.status_code == 409


def test_tagging_the_same_experience_with_no_nickname_twice_is_idempotent(client):
    slug = _register_and_project(client, "refs-idempotent@example.com")
    launched = _launch(client, slug)

    first = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/ref", json={})
    second = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/ref", json={})
    assert first.json() == second.json() == {"name": "ref v1.0.0", "experiment_id": launched["id"]}


def test_evolving_from_a_ref_name_works_like_any_other_ref(client):
    slug = _register_and_project(client, "refs-evolve@example.com")
    launched = _launch(client, slug)
    client.post(f"/api/projects/{slug}/experiences/{launched['id']}/ref", json={"name": "omega"})

    response = client.post(
        f"/api/projects/{slug}/experiences/omega/evoluer",
        json={"substrate": _substrate(), "steps": _steps(40), "title": "Suite", "intent": "Depuis omega"},
    )
    assert response.status_code == 201
    assert response.json()["id"] != launched["id"]


def test_refs_list_and_graph_condense_intermediate_versions(client):
    slug = _register_and_project(client, "refs-graph@example.com")
    root = _launch(client, slug, thickness=10)
    client.post(f"/api/projects/{slug}/experiences/{root['id']}/ref", json={"name": "omega"})

    # a lightweight evolution that doesn't change the process at all - version stays 1.0.0,
    # collapsed out of the ref graph the same way an unchanged commit is collapsed out of the
    # project's own version graph (spectre.core.versioning.determine_keep_ids).
    tagged = client.post(f"/api/projects/{slug}/experiences/{root['id']}/etiquettes", json={"tags": ["a-suivre"]}).json()

    # a real structural change (a step added) - bumps to 2.0.0
    grown = client.post(
        f"/api/projects/{slug}/experiences/{tagged['id']}/evoluer",
        json={
            "substrate": _substrate(),
            "steps": _steps(10) + [{"kind": "etch", "name": "Gravure", "recipe": "Anisotropic RIE", "depth": {"value": 5, "unit": "nm"}}],
            "title": "Suite",
            "intent": "Ajout d'une gravure",
        },
    ).json()
    client.post(f"/api/projects/{slug}/experiences/{grown['id']}/ref", json={"name": "banane"})

    items = client.get(f"/api/projects/{slug}/refs").json()["items"]
    version_by_name = {entry["names"][0]: entry["version"] for entry in items}
    assert version_by_name == {"omega": "1.0.0", "banane": "2.0.0"}

    graph = client.get(f"/api/projects/{slug}/refs/graphe").json()
    edges = {(e["from"], e["to"]) for e in graph["edges"]}
    # the ordinary commit ("tagged") in between is collapsed out - one edge straight from ref to ref
    assert edges == {(root["id"], grown["id"])}
