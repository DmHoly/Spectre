from __future__ import annotations


def _setup_project(client, email="owner@example.com", name="Owner"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    project = client.post("/api/projects", json={"name": "Salle blanche"}).json()
    return project["slug"]


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "recipe": "CVD Conformal",
            "thickness": {"value": 20, "unit": "nm"},
        }
    ]


def _plan():
    return {"step_index": 0, "field": "thickness", "values": [10, 20, 30]}


def test_preview_campaign_returns_svgs_and_variation(client):
    slug = _setup_project(client)
    response = client.post(
        f"/api/projects/{slug}/structures/variantes",
        json={"substrate": _substrate(), "steps": _steps(), "plan": _plan()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["svgs"]) == 3
    assert body["variation"]["entity_count"] == 3
    varying_paths = [f["path"] for f in body["variation"]["varying"]]
    assert varying_paths  # the deposited layer's geometry (its y-extent) varies with thickness
    assert all(p.startswith("layers[1]") for p in varying_paths)  # layer 0 is the untouched substrate
    varying_values = body["variation"]["varying"][0]["values"]
    assert sorted(varying_values) == [10.0, 20.0, 30.0]


def test_preview_campaign_rejects_non_numeric_field(client):
    slug = _setup_project(client)
    bad_plan = {"step_index": 0, "field": "material", "values": [1, 2]}
    response = client.post(
        f"/api/projects/{slug}/structures/variantes",
        json={"substrate": _substrate(), "steps": _steps(), "plan": bad_plan},
    )
    assert response.status_code == 422


def test_launch_campaign_and_read_matrix(client):
    slug = _setup_project(client)
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "plan": _plan(),
        "title": "Campagne epaisseur",
        "intent": "Explorer l'effet de l'epaisseur d'oxyde",
    }
    response = client.post(f"/api/projects/{slug}/experiences/campagne", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{experiment_id}").json()
    assert detail["is_batch"] is True
    assert "<svg" in detail["structure_svg"]

    matrix = client.get(f"/api/projects/{slug}/experiences/{experiment_id}/matrice").json()
    assert matrix["entity_count"] == 3
    assert len(matrix["varying"]) >= 1
    assert matrix["factor_label"] == "Épaisseur — Oxyde"
    assert matrix["factor_values"] == [10, 20, 30]


def test_matrice_endpoint_rejects_non_batch_experience(client):
    slug = _setup_project(client)
    single = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "Essai simple", "intent": "Verifier"},
    ).json()
    response = client.get(f"/api/projects/{slug}/experiences/{single['id']}/matrice")
    assert response.status_code == 400
