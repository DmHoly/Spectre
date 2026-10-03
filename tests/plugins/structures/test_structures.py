from __future__ import annotations

import os
from pathlib import Path

from spectre.plugins.structures import campaigns
from support.accounts import signup
from support.microprojects import join_as, signup_with_microproject
from support.structures import campaign_plan, list_materials, list_recipes, preview_campaign, simulate, steps, substrate


def _owner_microproject(client, email="owner@example.com", name="Owner"):
    return signup_with_microproject(client, email, "Salle blanche", name=name)


def test_list_materials(client):
    _owner_microproject(client)
    materials = list_materials(client)
    assert any(m["name"] == "Si" for m in materials)


def test_list_recipes_by_kind(client):
    _owner_microproject(client)
    recipes = list_recipes(client)
    assert any(r["name"] == "CVD Conformal" for r in recipes["deposition"])
    assert any(r["name"] == "Anisotropic RIE" for r in recipes["etch"])


def test_simulate_returns_one_svg_per_frame(client):
    _owner_microproject(client)
    response = simulate(client, {"substrate": substrate(), "steps": steps()})
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 2  # frame 0 (initial) + one per step
    assert "<svg" in body["frames"][-1]["svg"]


def test_any_signed_in_user_can_simulate_without_a_microproject(client):
    # un calcul, rien n'est enregistré : il suffit d'être connecté (l'anonyme a son 401, voir tests/contracts)
    signup(client, "nomicroproject@example.com")
    assert simulate(client, {"substrate": substrate(), "steps": steps()}).status_code == 200


def test_selective_growth_seed_ingan_matches_any_composition(client):
    _owner_microproject(client)
    process_steps = [
        {"kind": "epitaxial_growth", "name": "germe", "material": "In0.20Ga0.80N", "thickness": {"value": 20, "unit": "nm"}, "orientation": "c_plane", "seed_materials": []},
        # seed écrit "InGaN" en clair — doit être compris comme "n'importe quelle composition InGaN"
        {"kind": "epitaxial_growth", "name": "reprise selective", "material": "In0.30Ga0.70N", "thickness": {"value": 30, "unit": "nm"}, "orientation": "c_plane", "seed_materials": ["InGaN"]},
    ]
    body = simulate(client, {"substrate": substrate("GaN", width_nm=400), "steps": process_steps}).json()
    assert "In0.30Ga0.70N" in body["frames"][-1]["materials"]  # la reprise sélective a bien eu lieu


def test_simulate_accepts_a_flip_step_for_backside_processing(client):
    _owner_microproject(client)
    process_steps = [
        {"kind": "deposition", "name": "Metal avant", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 20, "unit": "nm"}},
        {"kind": "flip", "name": "Retournement"},
        {"kind": "deposition", "name": "Metal arriere", "material": "Ti", "recipe": "CVD Conformal", "thickness": {"value": 10, "unit": "nm"}},
    ]
    response = simulate(client, {"substrate": substrate(), "steps": process_steps})
    assert response.status_code == 200
    body = response.json()
    assert len(body["frames"]) == 4
    assert [f["step_kind"] for f in body["frames"][1:]] == ["deposition", "flip", "deposition"]


def test_simulate_rejects_a_flip_on_a_non_flat_surface(client):
    _owner_microproject(client)
    process_steps = [
        # a directional deposit through a resist opening leaves an isolated bump, narrower than
        # the domain - flip() should reject it rather than silently producing broken geometry.
        {"kind": "lithography", "name": "Masque", "resist_material": "Photoresist", "thickness": {"value": 20, "unit": "nm"}, "openings": [[80, 120]]},
        {"kind": "deposition", "name": "Plot", "material": "Au", "recipe": "Evaporation (normal)", "thickness": {"value": 15, "unit": "nm"}},
        {"kind": "resist_strip", "name": "Retrait resine"},
        {"kind": "flip", "name": "Retournement"},
    ]
    response = simulate(client, {"substrate": substrate(), "steps": process_steps})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"


def test_simulate_rejects_unknown_material(client):
    _owner_microproject(client)
    bad_substrate = {**substrate(), "material": "Vibranium"}
    response = simulate(client, {"substrate": bad_substrate, "steps": []})
    assert response.status_code == 422


def test_a_material_named_with_html_is_escaped_in_the_svg(client):
    # le nom d'un matériau de la bibliothèque éditable finit dans le <title> du SVG, que la page
    # insère par innerHTML
    hostile = '<img src=x onerror="alert(1)">'
    library = Path(os.environ["SPECTRE_LIBRARY_DIR"]) / "materiaux.yml"
    with library.open("a", encoding="utf-8") as out:
        out.write(f"\n  - name: '{hostile}'\n    category: other\n    color: \"#123456\"\n")
    _owner_microproject(client)
    assert any(m["name"] == hostile for m in list_materials(client))

    response = simulate(client, {"substrate": substrate(hostile), "steps": []})
    assert response.status_code == 200, response.text
    svg = response.json()["frames"][0]["svg"]
    assert "<img" not in svg
    assert "<title>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</title>" in svg
    assert 'fill="#123456"' in svg  # la couleur du matériau échappé est toujours la sienne


def test_campaign_preview_over_the_cap_is_refused_before_any_simulation(client, monkeypatch):
    _owner_microproject(client)
    simulated = []
    real = campaigns.run_simulation
    monkeypatch.setattr(campaigns, "run_simulation", lambda *args: simulated.append(args) or real(*args))
    monkeypatch.setattr(campaigns, "MAX_CAMPAIGN_ENTITIES", 4)
    # deux facteurs croisés : 3 x 2 = 6 variantes, au-delà du plafond
    plan = campaign_plan([10, 20, 30])
    plan["factors"].append({"step_index": -1, "field": "thickness", "values": [40, 50]})
    response = preview_campaign(client, {"substrate": substrate(), "steps": steps(), "plan": plan})
    assert response.status_code == 422
    assert "6 variantes : 4 au maximum" in response.json()["detail"]
    assert simulated == []

    response = preview_campaign(client, {"substrate": substrate(), "steps": steps(), "plan": campaign_plan([10, 20, 30, 40])})
    assert response.status_code == 200
    assert len(response.json()["svgs"]) == len(simulated) == 4


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
