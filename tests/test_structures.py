from __future__ import annotations

import pytest


def _register_and_create_project(client, email="owner@example.com", name="Owner", project_name="Salle blanche"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    project = client.post("/api/projects", json={"name": project_name}).json()
    return project["slug"]


def _substrate():
    return {"material": "Si", "domain_width": {"value": 200, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}


def _steps():
    return [
        {
            "kind": "deposition",
            "name": "Oxyde",
            "material": "SiO2",
            "mode": "conformal",
            "thickness": {"value": 20, "unit": "nm"},
        }
    ]


def test_list_materials(client):
    slug = _register_and_create_project(client)
    materials = client.get(f"/api/projects/{slug}/materials").json()
    assert any(m["name"] == "Si" for m in materials)


def test_simulate_returns_one_svg_per_frame(client):
    slug = _register_and_create_project(client)
    response = client.post(
        f"/api/projects/{slug}/structures/simulate", json={"substrate": _substrate(), "steps": _steps()}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 2  # frame 0 (initial) + one per step
    assert "<svg" in body["frames"][-1]["svg"]


def test_simulate_rejects_unknown_material(client):
    slug = _register_and_create_project(client)
    bad_substrate = {**_substrate(), "material": "Vibranium"}
    response = client.post(
        f"/api/projects/{slug}/structures/simulate", json={"substrate": bad_substrate, "steps": []}
    )
    assert response.status_code == 422


def test_launch_experience_creates_a_tracked_experiment(client):
    slug = _register_and_create_project(client)
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Ma premiere experience",
        "intent": "Verifier le depot d'oxyde",
        "objectives": [{"name": "Epaisseur cible", "metric": "thickness_nm", "direction": "target", "target": 20}],
    }
    response = client.post(f"/api/projects/{slug}/experiences", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]
    assert response.json()["branch"] == "ma-premiere-experience"

    listed = client.get(f"/api/projects/{slug}/experiences?status=running").json()
    assert any(item["id"] == experiment_id for item in listed["items"])


def test_viewer_cannot_launch_experience(client):
    slug = _register_and_create_project(client, "owner2@example.com", "Owner2")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "viewer2@example.com", "password": "supersecret", "name": "Viewer2"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner2@example.com", "password": "supersecret"})
    client.post(f"/api/projects/{slug}/members", json={"email": "viewer2@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "viewer2@example.com", "password": "supersecret"})
    response = client.post(
        f"/api/projects/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "X", "intent": "Y"},
    )
    assert response.status_code == 403
