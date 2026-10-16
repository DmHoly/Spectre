"""Une lithographie en sous-pixels : des zones côte à côte, chacune avec ses fils, son pas et son
ouverture, séparées par une distance. La lithographie porte sa disposition (``lattice_opening`` en mode
``zones``) : le serveur en recalcule les ouvertures et la largeur du domaine, sans réseau de fils."""

from __future__ import annotations

import pytest
from support.microprojects import signup_with_microproject
from support.structures import deposition, fixed_step_id, identified, length, lithography, preview_campaign, simulate

from spectre.plugins.structures import campaigns, simulation
from spectre.plugins.structures.schemas import ProcessInput

ZONES = [
    {"wires": 3, "pitch": 400, "diameter": 100},
    {"wires": 4, "pitch": 500, "diameter": 150},
    {"wires": 3, "pitch": 600, "diameter": 200},
]


def substrate(*, lattice: dict | None = None, width_nm: float = 123) -> dict:
    return {"material": "GaN", "domain_width": length(width_nm), "thickness": length(50), **({"lattice": lattice} if lattice else {})}


def zone_steps(gap: float = 400, zones: list[dict] | None = None) -> list[dict]:
    litho = {**lithography("Litho sous-pixels", thickness_nm=100, openings=[[0, 10]]), "lattice_opening": {"mode": "zones", "gap": gap, "zones": zones or ZONES}}
    return identified([deposition("Masque", "Si3N4", thickness_nm=30), litho, deposition("Couche", "SiO2", thickness_nm=10)])


def test_the_zones_set_the_domain_and_the_openings():
    body = ProcessInput.model_validate({"substrate": substrate(), "steps": zone_steps()})
    # 3 × 400 + 4 × 500 + 3 × 600 = 5000, trois zones : trois distances (une demi-distance de chaque côté du pixel)
    assert body.substrate.domain_width.to_nm() == 5000 + 3 * 400
    openings = body.steps[1].openings
    assert len(openings) == 10
    assert openings[0] == (200 + 150, 200 + 250)  # demi-distance, puis un fil au centre de sa maille de 400
    widths = [round(b - a, 3) for a, b in openings]
    assert widths == [100] * 3 + [150] * 4 + [200] * 3
    # la distance entre deux zones : le vide entre la dernière maille de l'une et la première de la suivante
    last_first_zone, first_second_zone = openings[2], openings[3]
    assert round(first_second_zone[0] - last_first_zone[1], 3) == 400 + (400 - 100) / 2 + (500 - 150) / 2
    assert body.lattice_anchors[1].mode == "zones"
    result = simulation.simulate_process(body.substrate, body.steps, lattice_anchors=body.lattice_anchors)
    assert result.frames[-1].domain_width_nm == 5000 + 3 * 400


def test_zones_do_not_need_a_lattice_and_win_over_it():
    with_lattice = ProcessInput.model_validate({"substrate": substrate(lattice={"pitch": 300, "wires": 2}), "steps": zone_steps()})
    assert with_lattice.substrate.domain_width.to_nm() == 6200
    assert len(with_lattice.steps[1].openings) == 10


def test_the_anchor_round_trips_compactly():
    opening = simulation.LatticeOpening.model_validate({"mode": "zones", "gap": 400, "zones": ZONES})
    assert opening.model_dump(mode="json") == {"mode": "zones", "gap": 400, "zones": ZONES}
    assert opening.with_size(800).gap == 800 and len(opening.with_size(800).zones) == 3
    with pytest.raises(ValueError):
        simulation.LatticeOpening.model_validate({"mode": "zones", "gap": 400})
    with pytest.raises(ValueError):
        simulation.LatticeOpening.model_validate({"mode": "wires", "diameter": 100, "zones": ZONES})


def test_a_hole_as_wide_as_its_pitch_is_refused(client):
    signup_with_microproject(client, "zones-wide@example.com", "Salle blanche")
    response = simulate(client, {"substrate": substrate(), "steps": zone_steps(zones=[{"wires": 2, "pitch": 400, "diameter": 400}])})
    assert response.status_code == 422 and "zone 1" in response.json()["detail"]
    assert simulate(client, {"substrate": substrate(), "steps": zone_steps()}).status_code == 200


def test_zones_and_a_lattice_anchored_lithography_do_not_mix(client):
    signup_with_microproject(client, "zones-mix@example.com", "Salle blanche")
    steps = zone_steps() + [{**lithography("Litho réseau", thickness_nm=100, openings=[[0, 10]]), "lattice_opening": {"diameter": 100}}]
    response = simulate(client, {"substrate": substrate(lattice={"pitch": 400, "wires": 1}), "steps": steps})
    assert response.status_code == 422 and "sous-pixels" in response.json()["detail"]


def test_a_campaign_varies_the_distance_between_sub_pixels(client):
    signup_with_microproject(client, "zones-campaign@example.com", "Salle blanche")
    plan = {"factors": [{"step_id": fixed_step_id(2), "field": "openings.gap", "values": [200, 800]}]}
    body = ProcessInput.model_validate({"substrate": substrate(), "steps": zone_steps()})
    variant = campaigns.VariantPlan.model_validate(plan)
    indexes = campaigns.factor_step_indexes(variant, body.step_ids)
    varied, steps, _declared = campaigns.apply_combination(body.substrate, body.steps, {}, variant, indexes, [800], body.lattice_anchors)
    assert varied.domain_width.to_nm() == 5000 + 3 * 800
    assert steps[1].openings[0][0] == 400 + (400 - 100) / 2

    preview = preview_campaign(client, {"substrate": substrate(), "steps": zone_steps(), "plan": plan})
    assert preview.status_code == 200 and len(preview.json()["svgs"]) == 2


def overridden_steps(thickness_by_zone: dict[int, float]) -> list[dict]:
    """Le procédé des sous-pixels, et une couche d'oxyde dont l'épaisseur diffère selon la zone."""
    steps = zone_steps(zones=[{"wires": 1, "pitch": 400, "diameter": 100}] * 3)
    layer = {**deposition("Couche", "SiO2", thickness_nm=10), "zone_overrides": {str(zone): {"thickness": length(nm)} for zone, nm in thickness_by_zone.items()}}
    return steps[:2] + [steps[2] | layer]


def top_of(frame, x_nm: float) -> float:
    """Le haut de la matière sous la verticale ``x_nm``, toutes couches confondues."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    solid = unary_union([layer.polygon for layer in frame.layers])
    cut = solid.intersection(LineString([(x_nm, -1000), (x_nm, 1000)]))
    return cut.bounds[3]


def test_a_step_takes_its_own_values_in_a_zone():
    body = ProcessInput.model_validate({"substrate": substrate(), "steps": overridden_steps({1: 60})})
    assert body.lattice_anchors[1].overrides_by_step() == {2: {1: {"thickness": length(60)}}}
    result = simulation.simulate_process(body.substrate, body.steps, lattice_anchors=body.lattice_anchors)
    width = body.substrate.domain_width.to_nm()
    assert width == 3 * 400 + 3 * 400 and len(result.frames) == 4
    assert all(f.domain_width_nm == width for f in result.frames)
    assert [len(o) for o in result.layer_origins] == [len(f.layers) for f in result.frames]
    assert len(set(result.frame_keys)) == 4
    last = result.frames[-1]
    # zones de 800 nm : leurs centres à 400, 1200, 2000 - le trou de chacune est à son centre, l'oxyde sur le masque à côté
    mask_top = [top_of(last, x) for x in (50, 850, 1650)]
    assert mask_top[0] == mask_top[2]  # les zones sans valeur propre se ressemblent
    assert mask_top[1] > mask_top[0] + 40  # celle qui a 60 nm d'oxyde au lieu de 10 monte plus haut


def test_zones_without_overrides_simulate_as_one_block():
    steps = overridden_steps({})
    body = ProcessInput.model_validate({"substrate": substrate(), "steps": steps})
    assert body.lattice_anchors[1].step_overrides is None
    assert simulation._zone_plan(body.steps, body.lattice_anchors) is None


def test_overrides_ride_on_the_stored_process_and_come_back():
    body = ProcessInput.model_validate({"substrate": substrate(), "steps": overridden_steps({0: 30, 2: 5})})
    stored = simulation.process_metadata(body.substrate, body.steps, lattice_anchors=body.lattice_anchors)
    assert "step_overrides" not in stored["steps"][1]["lattice_opening"]
    assert stored["steps"][2]["zone_overrides"] == {"0": {"thickness": length(30)}, "2": {"thickness": length(5)}}
    again = simulation.lattice_anchors_in(stored["steps"])
    assert again[1].overrides_by_step() == body.lattice_anchors[1].overrides_by_step()


def test_a_refused_value_names_the_step_and_the_zone(client):
    signup_with_microproject(client, "zones-bad@example.com", "Salle blanche")
    steps = overridden_steps({1: 60})
    steps[2]["zone_overrides"]["1"] = {"thickness": {"value": "beaucoup", "unit": "nm"}}
    response = simulate(client, {"substrate": substrate(), "steps": steps})
    assert response.status_code == 422 and "zone 2" in response.json()["detail"]
    steps[2]["zone_overrides"]["1"] = {"thickness": length(60)}
    assert simulate(client, {"substrate": substrate(), "steps": steps}).status_code == 200


def test_a_study_keeps_the_values_of_each_zone(client):
    from support.experiments import conclude, evolve, launch, process, versions

    slug = signup_with_microproject(client, "zones-study@example.com", "Salle blanche")
    study = launch(client, slug, substrate=substrate(), steps=overridden_steps({1: 60}))
    conclude(client, slug, study["id"], summary="Trois zones", decision="promote")
    editable = process(client, slug, study["id"])
    assert editable["steps"][2]["zone_overrides"] == {"1": {"thickness": length(60)}}
    assert editable["steps"][1]["lattice_opening"]["mode"] == "zones" and "step_overrides" not in editable["steps"][1]["lattice_opening"]

    # une autre valeur dans la zone : une autre structure
    evolve(client, slug, study["id"], title="Essai", intent="Verifier", substrate=substrate(), steps=overridden_steps({1: 90}))
    assert versions(client, slug, study["id"])[-1]["change_level"] != "none"


def test_a_zone_can_be_named_and_its_label_moved_without_changing_the_structure():
    named = [{**ZONES[0], "name": "Rouge", "offset": [120.0, -40.0]}, {**ZONES[1], "name": "  Vert "}, ZONES[2]]
    opening = simulation.LatticeOpening.model_validate({"mode": "zones", "gap": 400, "zones": named})
    dumped = opening.model_dump(mode="json")["zones"]
    assert dumped == [{**ZONES[0], "name": "Rouge", "offset": [120.0, -40.0]}, {**ZONES[1], "name": "Vert"}, ZONES[2]]  # sans nom ni décalage : la forme d'avant
    assert simulation.subpixel_layout(opening) == simulation.subpixel_layout(simulation.LatticeOpening.model_validate({"mode": "zones", "gap": 400, "zones": ZONES}))

    def process(zones: list[dict]) -> dict:
        steps = zone_steps(zones=zones)
        body = ProcessInput.model_validate({"substrate": substrate(), "steps": steps})
        return simulation.process_metadata(body.substrate, body.steps, lattice_anchors=body.lattice_anchors)

    assert simulation.view_neutral_process(process(named)) == simulation.view_neutral_process(process(ZONES))
    with pytest.raises(ValueError):
        simulation.LatticeOpening.model_validate({"mode": "zones", "gap": 400, "zones": [{**ZONES[0], "offset": [float("inf"), 0]}]})


def test_a_library_keeps_the_steps_a_measure_follows(client):
    """Une bibliothèque ne garde pas les ids d'étape : une cote suivie s'y range en positions (``also_at``)."""
    from support.process_library import create_item, get_item

    signup_with_microproject(client, "zones-follow@example.com", "Salle blanche")
    steps = zone_steps()
    label = {"text": "", "values": [], "measures": [{"direction": "thickness", "point": [10, 5], "scope": "material", "also_at": [2, 2, 1]}]}
    saved = create_item(client, "saved-structures", {"name": "Cotes suivies", "substrate": substrate(), "steps": steps, "layer_labels": {"1": label}}, scope="shared")
    measure = get_item(client, "saved-structures", saved["id"])["layer_labels"]["1"]["measures"][0]
    assert measure["also_at"] == [1, 2] and "also" not in measure
