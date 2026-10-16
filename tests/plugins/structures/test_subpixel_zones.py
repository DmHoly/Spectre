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
