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


def test_launch_stores_rationale_and_verification_method(client):
    client.post("/api/auth/register", json={"email": "obj@example.com", "password": "supersecret", "name": "O"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]

    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Essai",
        "intent": "Verifier isolation",
        "objectives": [
            {
                "name": "Isolation",
                "metric": "resistivity_ohm_cm",
                "direction": "target",
                "target": 1e6,
                "rationale": "condition pour passer en production",
                "verification_method": "mesure au profilometre",
            }
        ],
    }
    launched = client.post(f"/api/projects/{slug}/experiences", json=body).json()

    detail = client.get(f"/api/projects/{slug}/experiences/{launched['id']}").json()
    assert detail["objectives"][0]["rationale"] == "condition pour passer en production"
    assert detail["objective_verification"] == {"Isolation": "mesure au profilometre"}


def test_conclude_captures_reasoning_per_objective(client):
    client.post("/api/auth/register", json={"email": "obj2@example.com", "password": "supersecret", "name": "O2"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Essai",
        "intent": "Verifier",
        "objectives": [{"name": "Isolation", "metric": "r", "direction": "observe"}],
    }
    launched = client.post(f"/api/projects/{slug}/experiences", json=body).json()

    conclude_body = {
        "status": "concluded",
        "objective_results": [{"objective": "Isolation", "status": "met", "reasoning": "Mesure conforme a 1.2e6"}],
    }
    concluded = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/conclure", json=conclude_body).json()

    detail = client.get(f"/api/projects/{slug}/experiences/{concluded['id']}").json()
    assert detail["conclusion"]["objective_results"][0]["reasoning"] == "Mesure conforme a 1.2e6"


def test_evolve_carries_verification_when_objectives_unchanged(client):
    client.post("/api/auth/register", json={"email": "obj3@example.com", "password": "supersecret", "name": "O3"})
    slug = client.post("/api/projects", json={"name": "Projet"}).json()["slug"]
    body = {
        "substrate": _substrate(),
        "steps": _steps(20),
        "title": "Essai",
        "intent": "Verifier",
        "objectives": [
            {"name": "Isolation", "metric": "r", "direction": "observe", "verification_method": "profilometre"}
        ],
    }
    launched = client.post(f"/api/projects/{slug}/experiences", json=body).json()

    evolve_body = {"substrate": _substrate(), "steps": _steps(10), "title": "Essai", "intent": "Reduire"}
    evolved = client.post(f"/api/projects/{slug}/experiences/{launched['id']}/evoluer", json=evolve_body).json()

    detail = client.get(f"/api/projects/{slug}/experiences/{evolved['id']}").json()
    assert detail["objective_verification"] == {"Isolation": "profilometre"}
