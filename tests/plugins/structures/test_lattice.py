"""Le réseau de fils du gabarit SAG : le substrat porte un pas et un nombre de fils, la largeur du
domaine en suit, et une lithographie ancrée au réseau ouvre un trou par fil - recalculés par le
serveur, gardés par une étude, une campagne, une combinaison et la bibliothèque. Le nombre de fils
n'est qu'une vue : il ne fait pas de nouvelle version."""

from __future__ import annotations

from support.experiments import conclude, evolve, launch, process, versions
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item
from support.structures import deposition, fixed_step_id, identified, length, lithography, preview_campaign, simulate

from spectre.plugins.experiments import versioning
from spectre.plugins.structures import simulation
from spectre.plugins.structures.schemas import ProcessInput


def lattice_substrate(pitch: float = 400, wires: int = 1, *, width_nm: float = 123) -> dict:
    """Un substrat de GaN à réseau de fils - ``width_nm`` est une largeur périmée, que le réseau remplace."""
    return {"material": "GaN", "domain_width": length(width_nm), "thickness": length(50), "lattice": {"pitch": pitch, "wires": wires}}


def sag_steps(diameter: float = 100) -> list[dict]:
    """Un masque de nitrure, une lithographie ancrée au réseau (ses ouvertures, périmées, sont
    recalculées), la gravure du masque."""
    litho = {**lithography("Litho SAG", thickness_nm=100, openings=[[0, 10]]), "lattice_opening": {"diameter": diameter}}
    return identified([deposition("Masque", "Si3N4", thickness_nm=30), litho, deposition("Couche", "SiO2", thickness_nm=10)])


def test_the_lattice_sets_the_domain_and_one_opening_per_wire():
    body = ProcessInput.model_validate({"substrate": lattice_substrate(400, 5), "steps": sag_steps(100)})
    assert body.substrate.domain_width.to_nm() == 2000
    assert body.steps[1].openings == [(150, 250), (550, 650), (950, 1050), (1350, 1450), (1750, 1850)]
    assert body.lattice_anchors == {1: simulation.LatticeOpening(diameter=100)}

    one = ProcessInput.model_validate({"substrate": lattice_substrate(400, 1), "steps": sag_steps(100)})
    assert one.substrate.domain_width.to_nm() == 400 and one.steps[1].openings == [(150, 250)]
    result = simulation.simulate_process(one.substrate, one.steps)
    assert result.frames[-1].domain_width_nm == 400


def test_without_a_lattice_an_anchored_lithography_keeps_its_openings():
    body = ProcessInput.model_validate({"substrate": {**lattice_substrate(), "lattice": None}, "steps": sag_steps()})
    assert body.substrate.domain_width.to_nm() == 123
    assert body.steps[1].openings == [(0, 10)]
    assert "lattice" not in body.substrate.model_dump(mode="json")  # la forme d'avant


def test_an_opening_wider_than_the_pitch_is_refused(client):
    signup_with_microproject(client, "lattice-wide@example.com", "Salle blanche")
    response = simulate(client, {"substrate": lattice_substrate(400, 2), "steps": sag_steps(400)})
    assert response.status_code == 422
    assert "pas du réseau" in response.json()["detail"]
    assert simulate(client, {"substrate": lattice_substrate(400, 2), "steps": sag_steps(399)}).status_code == 200


def test_a_study_keeps_its_lattice_and_the_number_of_wires_is_only_a_view(client):
    slug = signup_with_microproject(client, "lattice-study@example.com", "Salle blanche")
    study = launch(client, slug, substrate=lattice_substrate(400, 1), steps=sag_steps(100))
    conclude(client, slug, study["id"], summary="Épi réglée sur un fil", decision="promote")

    editable = process(client, slug, study["id"])
    assert editable["substrate"]["lattice"] == {"pitch": 400, "wires": 1}
    assert editable["substrate"]["domain_width"]["value"] == 400
    assert editable["steps"][1]["lattice_opening"] == {"diameter": 100}
    assert editable["steps"][1]["openings"] == [[150, 250]]

    # le même procédé vu sur un pixel de six fils : la même structure, la conclusion reste
    pixel = evolve(client, slug, study["id"], title="Essai", intent="Verifier", substrate=lattice_substrate(400, 6), steps=sag_steps(100))
    assert versions(client, slug, study["id"])[-1]["change_level"] == "none"
    assert pixel["conclusion"]["summary"] == "Épi réglée sur un fil"
    assert process(client, slug, study["id"])["steps"][1]["openings"][-1] == [2150, 2250]

    # un autre pas, un autre diamètre : d'autres structures
    evolve(client, slug, study["id"], title="Essai", intent="Verifier", substrate=lattice_substrate(500, 6), steps=sag_steps(100))
    assert versions(client, slug, study["id"])[-1]["change_level"] == "major"
    evolve(client, slug, study["id"], title="Essai", intent="Verifier", substrate=lattice_substrate(500, 6), steps=sag_steps(120))
    assert versions(client, slug, study["id"])[-1]["change_level"] == "minor"


def test_the_view_does_not_count_in_the_signature():
    def metadata(wires: int, diameter: float = 100) -> dict:
        body = ProcessInput.model_validate({"substrate": lattice_substrate(400, wires), "steps": sag_steps(diameter)})
        return {"structureforge_process": simulation.process_metadata(body.substrate, body.steps, lattice_anchors=body.lattice_anchors)}

    assert versioning.structure_signature(metadata(1)) == versioning.structure_signature(metadata(6))
    assert versioning.structure_signature(metadata(1)) != versioning.structure_signature(metadata(1, 120))
    assert versioning.same_settings(metadata(1)["structureforge_process"], metadata(6)["structureforge_process"])


def test_a_campaign_varies_the_pitch_of_the_lattice_and_the_diameter_of_its_holes(client):
    slug = signup_with_microproject(client, "lattice-campaign@example.com", "Salle blanche")
    litho = fixed_step_id(2)
    plan = {
        "factors": [
            {"step_id": litho, "field": "openings.pitch", "values": [400, 600]},
            {"step_id": litho, "field": "openings.diameter", "values": [100, 200]},
        ]
    }
    body = ProcessInput.model_validate({"substrate": lattice_substrate(400, 2), "steps": sag_steps(100)})
    from spectre.plugins.structures import campaigns

    variant = campaigns.VariantPlan.model_validate(plan)
    indexes = campaigns.factor_step_indexes(variant, body.step_ids)
    substrate, steps, _declared = campaigns.apply_combination(body.substrate, body.steps, {}, variant, indexes, [600, 200], body.lattice_anchors)
    assert substrate.domain_width.to_nm() == 1200 and substrate.lattice.pitch == 600
    assert steps[1].openings == [(200, 400), (800, 1000)]

    preview = preview_campaign(client, {"substrate": lattice_substrate(400, 2), "steps": sag_steps(100), "plan": plan})
    assert preview.status_code == 200 and len(preview.json()["svgs"]) == 4

    # la largeur du domaine suit le réseau : elle ne se fait pas varier
    width = {"factors": [{"step_id": "substrate", "field": "domain_width", "values": [800, 1600]}]}
    refused = preview_campaign(client, {"substrate": lattice_substrate(400, 2), "steps": sag_steps(100), "plan": width})
    assert refused.status_code == 422

    # la variante d'une campagne lancée : le pas et le diamètre de sa plaque, toujours ancrés
    study = launch(client, slug, kind="campaign", substrate=lattice_substrate(400, 2), steps=sag_steps(100), plan=plan, entities=[])
    last = process(client, slug, study["id"], variant=3)
    assert last["substrate"]["lattice"] == {"pitch": 600, "wires": 2}
    assert last["steps"][1]["lattice_opening"] == {"diameter": 200}
    assert last["steps"][1]["openings"] == [[200, 400], [800, 1000]]


def test_the_library_keeps_the_anchors_of_a_published_study(client):
    slug = signup_with_microproject(client, "lattice-library@example.com", "Salle blanche")
    study = launch(client, slug, substrate=lattice_substrate(400, 3), steps=sag_steps(100))
    published = create_item(client, "saved-structures", {**process(client, slug, study["id"]), "name": "SAG 400"}, microproject=slug)
    saved = get_item(client, "saved-structures", published["id"])
    assert saved["substrate"]["lattice"] == {"pitch": 400, "wires": 3}
    assert saved["lattice_openings"] == {"1": {"diameter": 100}}
