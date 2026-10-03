from __future__ import annotations

from support.experiments import get_experience, launch
from support.microprojects import signup_with_microproject
from support.structures import deposition, lithography, steps, substrate


def _steps_two():
    return [deposition(), deposition("Nitrure", thickness_nm=10)]


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
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    response = client.post(
        "/api/campaign-previews",
        json={"substrate": substrate(), "steps": steps(), "plan": _plan()},
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


def test_preview_campaign_rejects_numbers_for_a_name_field(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    bad_plan = {"factors": [{"step_index": 0, "field": "material", "values": [1, 2]}]}
    response = client.post(
        "/api/campaign-previews",
        json={"substrate": substrate(), "steps": steps(), "plan": bad_plan},
    )
    assert response.status_code == 422


def test_preview_campaign_with_two_factors_is_fully_crossed(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    response = client.post(
        "/api/campaign-previews",
        json={"substrate": substrate(), "steps": _steps_two(), "plan": _plan_two_factors()},
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
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    body = {
        "substrate": substrate(),
        "steps": steps(),
        "plan": _plan(),
        "title": "Campagne epaisseur",
        "intent": "Explorer l'effet de l'epaisseur d'oxyde",
        "entities": [{"sample_id": "W1"}],
    }
    response = client.post(f"/api/microprojets/{slug}/experiences/campagne", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]

    detail = get_experience(client, slug, experiment_id)
    assert detail["is_batch"] is True
    assert "<svg" in detail["structure_svg"]

    matrix = client.get(f"/api/microprojets/{slug}/experiences/{experiment_id}/matrice").json()
    assert matrix["entity_count"] == 3
    assert len(matrix["varying"]) >= 1
    assert matrix["factor_labels"] == ["Épaisseur — Oxyde"]
    assert matrix["factor_values"] == [[10], [20], [30]]
    assert len(matrix["svgs"]) == 3
    assert all("<svg" in svg for svg in matrix["svgs"])
    assert matrix["labels"] == ["10", "20", "30"]


def test_launch_campaign_with_two_factors(client):
    slug = signup_with_microproject(client, "two-factors@example.com", "Salle blanche")
    body = {
        "substrate": substrate(),
        "steps": _steps_two(),
        "plan": _plan_two_factors(),
        "title": "Campagne croisee",
        "intent": "Explorer epaisseur et profondeur ensemble",
        "entities": [{"sample_id": "W1"}],
    }
    response = client.post(f"/api/microprojets/{slug}/experiences/campagne", json=body)
    assert response.status_code == 201
    experiment_id = response.json()["id"]

    matrix = client.get(f"/api/microprojets/{slug}/experiences/{experiment_id}/matrice").json()
    assert matrix["entity_count"] == 6
    assert matrix["factor_labels"] == ["Épaisseur — Oxyde", "Épaisseur — Nitrure"]
    assert len(matrix["factor_values"]) == 6
    assert all(len(row) == 2 for row in matrix["factor_values"])


def test_matrice_endpoint_rejects_non_batch_experience(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    single = launch(client, slug, title="Essai simple")
    response = client.get(f"/api/microprojets/{slug}/experiences/{single['id']}/matrice")
    assert response.status_code == 400


def test_preview_campaign_rejects_an_unknown_field(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    bad_plan = {"factors": [{"step_index": 0, "field": "vitesse_imaginaire", "values": [1, 2]}]}
    response = client.post(
        "/api/campaign-previews",
        json={"substrate": substrate(), "steps": steps(), "plan": bad_plan},
    )
    assert response.status_code == 422
    assert "thickness" in response.json()["detail"]  # the message lists what can be varied instead


def _preview(client, slug, process_steps, plan, declared_params=None):
    return client.post(
        "/api/campaign-previews",
        json={"substrate": substrate(), "steps": process_steps, "plan": plan, "declared_params": declared_params or {}},
    )


def test_campaign_can_vary_a_name_field_such_as_the_recipe(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    plan = {"factors": [{"step_index": 0, "field": "recipe", "values": ["CVD Conformal", "Sputter Metal (normal)"], "scale": "list"}]}
    response = _preview(client, slug, steps(), plan)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["labels"] == ["CVD Conformal", "Sputter Metal (normal)"]
    assert body["factor_labels"] == ["Recette — Oxyde"]


def test_campaign_can_vary_a_plain_number_field(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    process_steps = [
        {
            "kind": "epitaxial_growth",
            "name": "Coquille",
            "material": "GaN",
            "thickness": {"value": 10, "unit": "nm"},
            "orientation": "semi_polar",
            "angle_deg": 30,
            "seed_materials": [],
        }
    ]
    plan = {"factors": [{"step_index": 0, "field": "angle_deg", "values": [20, 45]}]}
    response = _preview(client, slug, process_steps, plan)
    assert response.status_code == 200, response.text
    assert response.json()["labels"] == ["20", "45"]


def test_campaign_can_vary_the_indium_rate_of_a_graded_nitride(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    process_steps = [deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial")]
    plan = {"factors": [{"step_index": 0, "field": "material.fraction", "values": [10, 30]}]}
    response = _preview(client, slug, process_steps, plan)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["factor_labels"] == ["Taux (%) — Puits"]
    assert body["labels"] == ["10", "30"]


def test_campaign_can_vary_the_substrate(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    plan = {"factors": [{"step_index": -1, "field": "thickness", "values": [40, 80]}]}
    response = _preview(client, slug, steps(), plan)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["factor_labels"] == ["Épaisseur — Substrat"]
    assert body["variation"]["varying"]  # the substrate layer itself changes


def test_campaign_can_vary_a_lithography_pitch(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    process_steps = [lithography("Masque", thickness_nm=30, openings=[[25, 55], [85, 115], [145, 175]])]
    plan = {"factors": [{"step_index": 0, "field": "openings.pitch", "values": [50, 60]}]}
    response = _preview(client, slug, process_steps, plan)
    assert response.status_code == 200, response.text
    assert response.json()["factor_labels"] == ["Pas du réseau — Masque"]

    overlapping = {"factors": [{"step_index": 0, "field": "openings.pitch", "values": [20]}]}
    assert _preview(client, slug, process_steps, overlapping).status_code == 422  # 30 nm openings on a 20 nm pitch


def test_campaign_varies_a_declared_parameter_on_a_log_scale_and_keeps_it(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    declared = {"0": [{"name": "dopage", "value": 1e18, "obtention": {"precurseur": "Cp2Mg"}}]}
    plan = {"factors": [{"step_index": 0, "field": "declared:dopage", "values": [1e17, 1e18, 1e19], "scale": "log"}]}

    preview = _preview(client, slug, steps(), plan, declared)
    assert preview.status_code == 200, preview.text
    assert preview.json()["labels"] == ["1e17", "1e18", "1e19"]  # never 100000000000000000
    assert preview.json()["factor_labels"] == ["dopage — Oxyde"]

    launched = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json={
            "substrate": substrate(),
            "steps": steps(),
            "plan": plan,
            "declared_params": declared,
            "title": "Campagne dopage",
            "intent": "Balayer le dopage sur trois decades",
            "entities": [{"sample_id": "W1"}],
        },
    )
    assert launched.status_code == 201, launched.text
    experiment_id = launched.json()["id"]

    matrix = client.get(f"/api/microprojets/{slug}/experiences/{experiment_id}/matrice").json()
    assert matrix["factor_scales"] == ["log"]
    assert matrix["factor_values"] == [[1e17], [1e18], [1e19]]
    assert matrix["labels"] == ["1e17", "1e18", "1e19"]

    process = client.get(f"/api/microprojets/{slug}/experiences/{experiment_id}/process").json()
    assert process["declared_params"] == {"0": [{"name": "dopage", "value": 1e18, "obtention": {"precurseur": "Cp2Mg"}}]}


def test_declared_parameters_are_kept_on_launch_and_evolution(client):
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    declared = {"0": [{"name": "dopage", "value": 2.5e18, "obtention": {}}]}
    launched = launch(client, slug, title="Essai dope", intent="Verifier que le dopage est garde", declared_params=declared)
    process = client.get(f"/api/microprojets/{slug}/experiences/{launched['id']}/process").json()
    assert process["declared_params"] == declared

    evolved = client.post(
        f"/api/microprojets/{slug}/experiences/{launched['id']}/evoluer",
        json={
            "substrate": substrate(),
            "steps": steps(),
            "declared_params": {"0": [{"name": "dopage", "value": 5e18, "obtention": {}}]},
            "title": "Essai dope",
            "intent": "Doubler le dopage",
        },
    )
    assert evolved.status_code == 201, evolved.text
    process = client.get(f"/api/microprojets/{slug}/experiences/{evolved.json()['id']}/process").json()
    assert process["declared_params"]["0"][0]["value"] == 5e18

    plain = launch(client, slug, title="Sans", intent="x", entities=[{"sample_id": "W2"}])
    assert "declared_params" not in client.get(f"/api/microprojets/{slug}/experiences/{plain['id']}/process").json()


def test_campaign_varying_the_outline_shape_still_previews_and_launches(client):
    """A facet growth rate changes how many points each outline has - Follow's point-by-point
    split can't compare those, the campaign must still go through (compared layer by layer)."""
    slug = signup_with_microproject(client, "owner@example.com", "Salle blanche")
    process_steps = [
        {
            "kind": "faceted_growth",
            "name": "Pointe",
            "material": "GaN",
            "thickness": {"value": 10, "unit": "nm"},
            "rate_c": 1.0,
            "rate_m": 0.25,
            "rate_sp": 0.5,
            "semi_polar_angle_deg": 30,
            "seed_materials": [],
        }
    ]
    plan = {"factors": [{"step_index": 0, "field": "rate_sp", "values": [0.2, 0.9], "scale": "linear"}]}
    preview = _preview(client, slug, process_steps, plan)
    assert preview.status_code == 200, preview.text
    launched = client.post(
        f"/api/microprojets/{slug}/experiences/campagne",
        json={"substrate": substrate(), "steps": process_steps, "plan": plan, "title": "Facettes", "intent": "x", "entities": [{"sample_id": "W1"}]},
    )
    assert launched.status_code == 201, launched.text
    matrix = client.get(f"/api/microprojets/{slug}/experiences/{launched.json()['id']}/matrice")
    assert matrix.status_code == 200
    assert matrix.json()["entity_count"] == 2


def test_analyze_variants_compares_layer_extents_when_outlines_differ_in_shape():
    from follow.core.errors import BatchShapeError
    from follow.doe.batch import analyze_batch
    from structureforge.adapters.follow_adapter import LayerSpec, ProcessStructure

    from spectre.plugins.structures.campaigns import analyze_variants

    def entry(points):
        return ProcessStructure(domain_width_nm=100, layers=[LayerSpec(material="GaN", rings=[{"exterior": points, "interiors": []}])])

    square = entry([[0, 0], [100, 0], [100, 10], [0, 10], [0, 0]])
    pointed = entry([[0, 0], [100, 0], [100, 10], [50, 25], [0, 10], [0, 0]])
    try:
        analyze_batch([square, pointed])
        raise AssertionError("expected Follow to refuse differently-shaped outlines")
    except BatchShapeError:
        pass

    variation = analyze_variants([square, pointed])
    assert variation.entity_count == 2
    assert [f.path for f in variation.varying] == ["layers[0].y_max"]  # 10 -> 25, the only difference
