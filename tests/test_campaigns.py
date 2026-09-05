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


def _steps_two():
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "recipe": "CVD Conformal",
            "thickness": {"value": 20, "unit": "nm"},
        },
        {
            "kind": "deposition",
            "name": "Nitrure",
            "material": "SiO2",
            "recipe": "CVD Conformal",
            "thickness": {"value": 10, "unit": "nm"},
        },
    ]


def _plan():
    return {"factors": [{"step_index": 0, "field": "thickness", "values": [10, 20, 30]}]}


def _plan_two_factors():
    return {
        "factors": [
            {"step_index": 0, "field": "thickness", "values": [10, 20]},
            {"step_index": 1, "field": "thickness", "values": [5, 15, 25]},
        ]
    }


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
    bad_plan = {"factors": [{"step_index": 0, "field": "material", "values": [1, 2]}]}
    response = client.post(
        f"/api/projects/{slug}/structures/variantes",
        json={"substrate": _substrate(), "steps": _steps(), "plan": bad_plan},
    )
    assert response.status_code == 422


def test_preview_campaign_with_two_factors_is_fully_crossed(client):
    slug = _setup_project(client)
    response = client.post(
        f"/api/projects/{slug}/structures/variantes",
        json={"substrate": _substrate(), "steps": _steps_two(), "plan": _plan_two_factors()},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["svgs"]) == 6  # 2 thicknesses x 3 depths, fully crossed
    assert body["variation"]["entity_count"] == 6
    assert body["factor_labels"] == ["Épaisseur — Oxyde", "Épaisseur — Nitrure"]
    assert len(body["factor_values"]) == 6
    assert all(len(row) == 2 for row in body["factor_values"])
    assert sorted(body["labels"]) == sorted(
        f"{t} · {d}" for t in (10, 20) for d in (5, 15, 25)
    )


def test_launch_campaign_and_read_matrix(client):
    slug = _setup_project(client)
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "plan": _plan(),
        "title": "Campagne epaisseur",
        "intent": "Explorer l'effet de l'epaisseur d'oxyde",
        "entities": [{"sample_id": "W1"}],
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
    assert matrix["factor_labels"] == ["Épaisseur — Oxyde"]
    assert matrix["factor_values"] == [[10], [20], [30]]
    assert len(matrix["svgs"]) == 3
    assert all("<svg" in svg for svg in matrix["svgs"])
    assert matrix["labels"] == ["10", "20", "30"]


def test_launch_campaign_with_two_factors(client):
    slug = _setup_project(client, email="two-factors@example.com")
    body = {
        "substrate": _substrate(),
        "steps": _steps_two(),
        "plan": _plan_two_factors(),
        "title": "Campagne croisee",
        "intent": "Explorer epaisseur et profondeur ensemble",
        "entities": [{"sample_id": "W1"}],
    }
    response = client.post(f"/api/projects/{slug}/experiences/campagne", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]

    matrix = client.get(f"/api/projects/{slug}/experiences/{experiment_id}/matrice").json()
    assert matrix["entity_count"] == 6
    assert matrix["factor_labels"] == ["Épaisseur — Oxyde", "Épaisseur — Nitrure"]
    assert len(matrix["factor_values"]) == 6
    assert all(len(row) == 2 for row in matrix["factor_values"])


def test_matrice_endpoint_rejects_non_batch_experience(client):
    slug = _setup_project(client)
    single = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Essai simple",
            "intent": "Verifier",
            "entities": [{"sample_id": "W1"}],
        },
    ).json()
    response = client.get(f"/api/projects/{slug}/experiences/{single['id']}/matrice")
    assert response.status_code == 400
