from __future__ import annotations


def _setup_project(client, email="owner@example.com", name="Owner"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    project = client.post("/api/projects", json={"name": "Salle blanche"}).json()
    return project["slug"]


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


def _launch(client, slug, title="Essai initial", thickness=20):
    body = {
        "substrate": _substrate(),
        "steps": _steps(thickness),
        "title": title,
        "intent": "Verifier l'isolation",
        "objectives": [{"name": "Isolation", "metric": "resistivity_ohm_cm", "direction": "target", "target": 1e6}],
    }
    return client.post(f"/api/projects/{slug}/experiences", json=body).json()


def test_get_experience_detail_has_structure_svg(client):
    slug = _setup_project(client)
    launched = _launch(client, slug)

    response = client.get(f"/api/projects/{slug}/experiences/{launched['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Essai initial"
    assert body["status"] == "draft"
    assert "<svg" in body["structure_svg"]
    assert body["has_editable_process"] is True


def test_process_endpoint_returns_editable_recipe(client):
    slug = _setup_project(client)
    launched = _launch(client, slug)

    response = client.get(f"/api/projects/{slug}/experiences/{launched['id']}/process")
    assert response.status_code == 200
    body = response.json()
    assert body["substrate"]["material"] == "Si"
    assert body["steps"][0]["kind"] == "deposition"


def test_evolve_then_timeline_and_diff(client):
    slug = _setup_project(client)
    launched = _launch(client, slug, thickness=20)

    evolve_body = {
        "substrate": _substrate(),
        "steps": _steps(thickness=10),
        "title": "Essai initial",
        "intent": "Reduire l'epaisseur",
        "objectives": [],
    }
    evolved = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/evoluer", json=evolve_body)
    assert evolved.status_code == 201
    evolved_id = evolved.json()["id"]

    timeline = client.get(f"/api/projects/{slug}/experiences/{evolved_id}/timeline").json()
    assert [item["id"] for item in timeline["items"]] == [launched["id"], evolved_id]
    assert timeline["items"][-1]["is_current"] is True

    diff = client.get(f"/api/projects/{slug}/experiences/{evolved_id}/diff").json()
    assert diff["target"] == launched["id"]
    assert len(diff["entries"]) >= 1


def test_conclude_experience(client):
    slug = _setup_project(client)
    launched = _launch(client, slug)

    body = {
        "status": "concluded",
        "decision": "promote",
        "summary": "Objectif atteint.",
        "objective_results": [{"objective": "Isolation", "status": "met", "reasoning": "Mesure conforme"}],
    }
    response = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/conclure", json=body)
    assert response.status_code == 201
    concluded_id = response.json()["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{concluded_id}").json()
    assert detail["status"] == "concluded"
    assert detail["conclusion"]["decision"] == "promote"

    concluded_list = client.get(f"/api/projects/{slug}/experiences?status=concluded").json()
    assert any(item["id"] == concluded_id for item in concluded_list["items"])


def test_viewer_cannot_evolve_or_conclude(client):
    slug = _setup_project(client, "owner4@example.com", "Owner4")
    launched = _launch(client, slug)

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "viewer4@example.com", "password": "supersecret", "name": "Viewer4"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner4@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "viewer4@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "viewer4@example.com", "password": "supersecret"})

    evolve = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/evoluer",
        json={"substrate": _substrate(), "steps": _steps(), "title": "X", "intent": "Y"},
    )
    assert evolve.status_code == 403

    conclude = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/conclure", json={"status": "concluded"})
    assert conclude.status_code == 403
