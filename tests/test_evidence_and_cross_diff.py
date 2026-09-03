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
