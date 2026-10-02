from __future__ import annotations

from support.microprojects import join_as, signup_with_microproject
from support.structures import steps, substrate


def _owner_microproject(client, email="owner@example.com", name="Owner"):
    return signup_with_microproject(client, email, "Salle blanche", name=name)


def test_list_materials(client):
    slug = _owner_microproject(client)
    materials = client.get(f"/api/microprojets/{slug}/materials").json()
    assert any(m["name"] == "Si" for m in materials)


def test_simulate_returns_one_svg_per_frame(client):
    slug = _owner_microproject(client)
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": substrate(), "steps": steps()}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 2  # frame 0 (initial) + one per step
    assert "<svg" in body["frames"][-1]["svg"]


def test_selective_growth_seed_ingan_matches_any_composition(client):
    slug = _owner_microproject(client)
    process_steps = [
        {"kind": "epitaxial_growth", "name": "germe", "material": "In0.20Ga0.80N", "thickness": {"value": 20, "unit": "nm"}, "orientation": "c_plane", "seed_materials": []},
        # seed écrit "InGaN" en clair — doit être compris comme "n'importe quelle composition InGaN"
        {"kind": "epitaxial_growth", "name": "reprise selective", "material": "In0.30Ga0.70N", "thickness": {"value": 30, "unit": "nm"}, "orientation": "c_plane", "seed_materials": ["InGaN"]},
    ]
    body = client.post(f"/api/microprojets/{slug}/structures/simulate", json={"substrate": substrate("GaN", width_nm=400), "steps": process_steps}).json()
    assert "In0.30Ga0.70N" in body["frames"][-1]["materials"]  # la reprise sélective a bien eu lieu


def test_simulate_accepts_a_flip_step_for_backside_processing(client):
    slug = _owner_microproject(client)
    process_steps = [
        {"kind": "deposition", "name": "Metal avant", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 20, "unit": "nm"}},
        {"kind": "flip", "name": "Retournement"},
        {"kind": "deposition", "name": "Metal arriere", "material": "Ti", "recipe": "CVD Conformal", "thickness": {"value": 10, "unit": "nm"}},
    ]
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": substrate(), "steps": process_steps}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 4
    assert [f["step_kind"] for f in body["frames"][1:]] == ["deposition", "flip", "deposition"]


def test_simulate_rejects_a_flip_on_a_non_flat_surface(client):
    slug = _owner_microproject(client)
    process_steps = [
        # a directional deposit through a resist opening leaves an isolated bump, narrower than
        # the domain - flip() should reject it rather than silently producing broken geometry.
        {"kind": "lithography", "name": "Masque", "resist_material": "Photoresist", "thickness": {"value": 20, "unit": "nm"}, "openings": [[80, 120]]},
        {"kind": "deposition", "name": "Plot", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 15, "unit": "nm"}},
        {"kind": "resist_strip", "name": "Retrait resine"},
        {"kind": "flip", "name": "Retournement"},
    ]
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": substrate(), "steps": process_steps}
    )
    assert response.status_code == 422


def test_simulate_rejects_unknown_material(client):
    slug = _owner_microproject(client)
    bad_substrate = {**substrate(), "material": "Vibranium"}
    response = client.post(
        f"/api/microprojets/{slug}/structures/simulate", json={"substrate": bad_substrate, "steps": []}
    )
    assert response.status_code == 422


def test_launch_experience_creates_a_tracked_experiment(client):
    slug = _owner_microproject(client)
    body = {
        "substrate": substrate(),
        "steps": steps(),
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
    slug = _owner_microproject(client, "owner2@example.com", "Owner2")
    join_as(client, slug, "viewer2@example.com", owner="owner2@example.com", role="viewer", name="Viewer2")
    response = client.post(
        f"/api/microprojets/{slug}/experiences",
        json={"substrate": substrate(), "steps": steps(), "title": "X", "intent": "Y"},
    )
    assert response.status_code == 403
