from __future__ import annotations

import pytest


def _register_and_create_microproject(client, email="owner@example.com", name="Owner", microproject_name="Salle blanche"):
    client.post("/api/auth/register", json={"email": email, "password": "supersecret", "name": name})
    microproject = client.post("/api/microprojets", json={"name": microproject_name}).json()
    return microproject["slug"]


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


def test_list_materials(client):
    slug = _register_and_create_microproject(client)
    materials = client.get(f"/api/microprojets/{slug}/materials").json()
    assert any(m["name"] == "Si" for m in materials)


def test_simulate_returns_one_svg_per_frame(client):
    slug = _register_and_create_microproject(client)
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": _substrate(), "steps": _steps()}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 2  # frame 0 (initial) + one per step
    assert "<svg" in body["frames"][-1]["svg"]


def test_selective_growth_seed_ingan_matches_any_composition(client):
    slug = _register_and_create_microproject(client)
    substrate = {"material": "GaN", "domain_width": {"value": 400, "unit": "nm"}, "thickness": {"value": 50, "unit": "nm"}}
    steps = [
        {"kind": "epitaxial_growth", "name": "germe", "material": "In0.20Ga0.80N", "thickness": {"value": 20, "unit": "nm"}, "orientation": "c_plane", "seed_materials": []},
        # seed écrit "InGaN" en clair — doit être compris comme "n'importe quelle composition InGaN"
        {"kind": "epitaxial_growth", "name": "reprise selective", "material": "In0.30Ga0.70N", "thickness": {"value": 30, "unit": "nm"}, "orientation": "c_plane", "seed_materials": ["InGaN"]},
    ]
    body = client.post(f"/api/microprojets/{slug}/structures/simulate", json={"substrate": substrate, "steps": steps}).json()
    assert "In0.30Ga0.70N" in body["frames"][-1]["materials"]  # la reprise sélective a bien eu lieu


def test_simulate_accepts_a_flip_step_for_backside_processing(client):
    slug = _register_and_create_microproject(client)
    steps = [
        {"kind": "deposition", "name": "Metal avant", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 20, "unit": "nm"}},
        {"kind": "flip", "name": "Retournement"},
        {"kind": "deposition", "name": "Metal arriere", "material": "Ti", "recipe": "CVD Conformal", "thickness": {"value": 10, "unit": "nm"}},
    ]
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": _substrate(), "steps": steps}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 4
    assert [f["step_kind"] for f in body["frames"][1:]] == ["deposition", "flip", "deposition"]


def test_simulate_rejects_a_flip_on_a_non_flat_surface(client):
    slug = _register_and_create_microproject(client)
    steps = [
        # a directional deposit through a resist opening leaves an isolated bump, narrower than
        # the domain - flip() should reject it rather than silently producing broken geometry.
        {"kind": "lithography", "name": "Masque", "resist_material": "Photoresist", "thickness": {"value": 20, "unit": "nm"}, "openings": [[80, 120]]},
        {"kind": "deposition", "name": "Plot", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 15, "unit": "nm"}},
        {"kind": "resist_strip", "name": "Retrait resine"},
        {"kind": "flip", "name": "Retournement"},
    ]
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": _substrate(), "steps": steps}
    )
    assert response.status_code == 422


def test_simulate_rejects_unknown_material(client):
    slug = _register_and_create_microproject(client)
    bad_substrate = {**_substrate(), "material": "Vibranium"}
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": bad_substrate, "steps": []}
    )
    assert response.status_code == 422


def test_launch_experience_creates_a_tracked_experiment(client):
    slug = _register_and_create_microproject(client)
    body = {
        "substrate": _substrate(),
        "steps": _steps(),
        "title": "Ma premiere experience",
        "intent": "Verifier le depot d'oxyde",
        "objectives": [{"name": "Epaisseur cible", "metric": "thickness_nm", "direction": "target", "target": 20}],
        "entities": [{"sample_id": "W1"}],
    }
    response = client.post(f"/api/microprojets/{slug}/experiences", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]
    assert response.json()["branch"] == "ma-premiere-experience"

    listed = client.get(f"/api/microprojets/{slug}/experiences?status=running").json()
    assert any(item["id"] == experiment_id for item in listed["items"])


def test_viewer_cannot_launch_experience(client):
    slug = _register_and_create_microproject(client, "owner2@example.com", "Owner2")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"email": "viewer2@example.com", "password": "supersecret", "name": "Viewer2"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner2@example.com", "password": "supersecret"})
    client.post(f"/api/microprojets/{slug}/members", json={"email": "viewer2@example.com", "role": "viewer"})

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "viewer2@example.com", "password": "supersecret"})
    response = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": _substrate(), "steps": _steps(), "title": "X", "intent": "Y"},
    )
    assert response.status_code == 403
