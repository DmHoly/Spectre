from __future__ import annotations


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps(thickness=20):
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "recipe": "CVD Conformal",
            "thickness": {"value": thickness, "unit": "nm"},
        }
    ]


def _launch(client, slug, title="Essai"):
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": title,
        "intent": "Verifier",
        "entities": [{"sample_id": "W1"}],
    }
    return client.post(f"/api/projects/{slug}/experiences", json=body).json()


def test_add_evidence_creates_a_new_version_and_carries_forward(client):
    client.post("/api/auth/register", json={"email": "owner@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    body = {
        "description": "Mesure d'epaisseur au profilometre",
        "source": "https://labo.example/mesures/142",
        "metric_name": "thickness_nm",
        "metric_value": 20.3,
        "metric_unit": "nm",
    }
    response = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/preuves", json=body)
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert new_id != launched["id"]

    detail = client.get(f"/api/projects/{slug}/experiences/{new_id}").json()
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure d'epaisseur au profilometre"
    assert detail["evidence"][0]["metrics"]["thickness_nm"]["value"] == 20.3

    # a second piece of evidence carries the first one forward
    second = client.post(
        f"/api/projects/{slug}/experiences/{new_id}/preuves",
        json={"description": "Deuxieme mesure", "source": "https://labo.example/mesures/143"},
    )
    detail2 = client.get(f"/api/projects/{slug}/experiences/{second.json()['id']}").json()
    assert len(detail2["evidence"]) == 2


def test_concluding_an_experience_keeps_its_evidence(client):
    client.post("/api/auth/register", json={"email": "owner-concl@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Mesure d'epaisseur au profilometre", "source": "https://labo.example/mesures/142"},
    ).json()["id"]

    concluded = client.post(f"/api/projects/{slug}/experiences/{with_evidence}/conclure", json={"status": "concluded"})
    assert concluded.status_code == 201

    detail = client.get(f"/api/projects/{slug}/experiences/{concluded.json()['id']}").json()
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure d'epaisseur au profilometre"


def test_viewer_cannot_add_evidence(client):
    client.post("/api/auth/register", json={"email": "owner2@example.com", "password": "supersecret", "name": "O"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "viewer5@example.com", "password": "supersecret", "name": "V"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner2@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "viewer5@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "viewer5@example.com", "password": "supersecret"})
    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y"},
    )
    assert response.status_code == 403


def test_evidence_step_index_round_trips_and_is_labeled_in_the_process(client):
    client.post("/api/auth/register", json={"email": "owner-step@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={
            "description": "Mesure de perf apres depot",
            "source": "https://labo.example/mesures/1",
            "metric_name": "perf",
            "metric_value": 12.5,
            "step_index": 0,
        },
    )
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{response.json()['id']}").json()
    assert detail["evidence"][0]["step_index"] == 0

    # omitting step_index still defaults to None (not tied to any step)
    without_step = client.post(
        f"/api/projects/{slug}/experiences/{response.json()['id']}/preuves",
        json={"description": "Preuve generale", "source": "https://labo.example/mesures/2"},
    ).json()
    detail2 = client.get(f"/api/projects/{slug}/experiences/{without_step['id']}").json()
    assert detail2["evidence"][-1]["step_index"] is None


def test_evidence_step_index_must_be_within_process_bounds(client):
    client.post("/api/auth/register", json={"email": "owner-bounds@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)  # a single-step process (_steps() above)

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Hors bornes", "source": "y", "step_index": 5},
    )
    assert response.status_code == 422

    negative = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Negatif", "source": "y", "step_index": -1},
    )
    assert negative.status_code == 422


def test_evolving_an_experience_preserves_its_evidence_and_tags(client):
    client.post("/api/auth/register", json={"email": "owner-evolve@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    with_evidence = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "Mesure avant evolution", "source": "https://labo.example/mesures/1"},
    ).json()
    with_tag = client.post(
        f"/api/projects/{slug}/experiences/{with_evidence['id']}/etiquettes", json={"tags": ["important"]}
    ).json()

    evolve_body = {
        "substrate": _substrate(),
        "steps": _steps(thickness=10),
        "title": "Essai",
        "intent": "Reduire l'epaisseur",
        "objectives": [],
    }
    evolved = client.post(f"/api/projects/{slug}/experiences/{with_tag['id']}/evoluer", json=evolve_body)
    assert evolved.status_code == 201

    detail = client.get(f"/api/projects/{slug}/experiences/{evolved.json()['id']}").json()
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["description"] == "Mesure avant evolution"
    assert detail["tags"] == ["important"]


def test_cross_project_diff(client):
    client.post("/api/auth/register", json={"email": "cross@example.com", "password": "supersecret", "name": "Cross"})
    slug_a = client.post("/api/projects", json={"name": "Projet A"}).json()["slug"]
    slug_b = client.post("/api/projects", json={"name": "Projet B"}).json()["slug"]

    exp_a = _launch(client, slug_a, title="Essai A")
    exp_b_body = {
        "substrate": _substrate(),
        "steps": _steps(thickness=40),
        "title": "Essai B",
        "intent": "Verifier",
        "entities": [{"sample_id": "W2"}],
    }
    exp_b = client.post(f"/api/projects/{slug_b}/experiences", json=exp_b_body).json()

    response = client.get(
        f"/api/projects/{slug_a}/experiences/{exp_a['id']}/diff-externe"
        f"?autre_projet={slug_b}&autre_experience={exp_b['id']}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == exp_b["id"]
    assert body["target_project"] == "Projet B"
    assert len(body["entries"]) >= 1


def test_cross_project_diff_requires_access_to_other_project(client):
    client.post("/api/auth/register", json={"email": "ownerC@example.com", "password": "supersecret", "name": "C"})
    slug_c = client.post("/api/projects", json={"name": "Projet C"}).json()["slug"]
    exp_c = _launch(client, slug_c, title="Essai C")

    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "ownerD@example.com", "password": "supersecret", "name": "D"})
    slug_d = client.post("/api/projects", json={"name": "Projet D privé"}).json()["slug"]
    exp_d = _launch(client, slug_d, title="Essai D")

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "ownerC@example.com", "password": "supersecret"})
    response = client.get(
        f"/api/projects/{slug_c}/experiences/{exp_c['id']}/diff-externe"
        f"?autre_projet={slug_d}&autre_experience={exp_d['id']}"
    )
    assert response.status_code == 403


def test_evidence_kind_objective_and_interpretation_round_trip(client):
    client.post("/api/auth/register", json={"email": "owner-kind@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = client.post(
        f"/api/projects/{slug}/experiences",
        json={
            "substrate": _substrate(),
            "steps": _steps(),
            "title": "Essai",
            "intent": "Verifier",
            "entities": [{"sample_id": "W1"}],
            "objectives": [{"name": "Isolation", "metric": "resistivity_ohm_cm", "direction": "target", "target": 1e6}],
        },
    ).json()

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={
            "description": "Split vs PL",
            "source": "—",
            "kind": "graph",
            "objective": "Isolation",
            "interpretation": "L'isolation augmente avec l'epaisseur, coherent avec le changement",
            "graph_config": {"title": "Split vs PL", "x_label": "Epaisseur (nm)", "y_label": "Intensite PL", "query": "TODO", "data_source_url": None},
        },
    )
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{response.json()['id']}").json()
    evidence = detail["evidence"][0]
    assert evidence["kind"] == "graph"
    assert evidence["objective"] == "Isolation"
    assert evidence["interpretation"].startswith("L'isolation")
    assert evidence["graph_config"]["query"] == "TODO"


def test_evidence_objective_must_exist_on_the_experience(client):
    client.post("/api/auth/register", json={"email": "owner-badobj@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y", "objective": "Objectif inexistant"},
    )
    assert response.status_code == 422


def test_evidence_kind_defaults_to_standard(client):
    client.post("/api/auth/register", json={"email": "owner-default@example.com", "password": "supersecret", "name": "Owner"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    launched = _launch(client, slug)

    response = client.post(
        f"/api/projects/{slug}/experiences/{launched['id']}/preuves",
        json={"description": "x", "source": "y"},
    )
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{slug}/experiences/{response.json()['id']}").json()
    assert detail["evidence"][0]["kind"] == "standard"
    assert detail["evidence"][0]["objective"] is None
    assert detail["evidence"][0]["image_annotations"] == []
