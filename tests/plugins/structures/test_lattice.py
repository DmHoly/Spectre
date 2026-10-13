"""Le réseau de fils du gabarit SAG : le substrat porte un pas et un nombre de fils, la largeur du
domaine en suit, et une lithographie ancrée au réseau ouvre un trou par fil - recalculés par le
serveur, gardés par une étude, une campagne, une combinaison et la bibliothèque. Le nombre de fils
n'est qu'une vue : il ne fait pas de nouvelle version."""

from __future__ import annotations

from collections import OrderedDict

import pytest
import shapely
from shapely.affinity import translate
from support.experiments import conclude, evolve, launch, process, versions
from support.microprojects import signup_with_microproject
from support.process_library import create_item, get_item
from support.structures import deposition, etch, fixed_step_id, identified, length, lithography, preview_campaign, simulate

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


def anchored(mode: str, **size: float) -> list[dict]:
    """Le gabarit de sag_steps, la lithographie ancrée « mode » (``between``, ``pixel``...)."""
    steps = sag_steps()
    steps[1] = {**steps[1], "lattice_opening": {"mode": mode, **size}}
    return steps


def test_an_opening_between_the_wires_and_one_over_the_whole_pixel():
    between = ProcessInput.model_validate({"substrate": lattice_substrate(400, 2), "steps": anchored("between", width=100)})
    # entre deux fils voisins, et une demi-ouverture à chaque bord (le réseau se répète)
    assert between.steps[1].openings == [(0, 50), (350, 450), (750, 800)]
    pixel = ProcessInput.model_validate({"substrate": lattice_substrate(400, 3), "steps": anchored("pixel", margin=100)})
    assert pixel.steps[1].openings == [(100, 1100)]

    # chaque mode a sa taille ; un trou par fil s'écrit comme avant, sans son mode
    assert simulation.LatticeOpening(diameter=80).model_dump(mode="json") == {"diameter": 80}
    assert simulation.LatticeOpening(mode="pixel", margin=0, diameter=3).model_dump(mode="json") == {"mode": "pixel", "margin": 0}
    assert simulation.lattice_anchors_in(anchored("between", diameter=100)) == {}  # pas de largeur : ignorée


def test_an_anchored_opening_that_does_not_fit_is_refused(client):
    signup_with_microproject(client, "lattice-fit@example.com", "Salle blanche")
    margin = simulate(client, {"substrate": lattice_substrate(400, 1), "steps": anchored("pixel", margin=200)})
    assert margin.status_code == 422 and "marge" in margin.json()["detail"]
    width = simulate(client, {"substrate": lattice_substrate(400, 2), "steps": anchored("between", width=400)})
    assert width.status_code == 422 and "entre les fils" in width.json()["detail"]


def test_a_campaign_varies_the_size_of_its_own_anchor(client):
    signup_with_microproject(client, "lattice-modes@example.com", "Salle blanche")
    litho = fixed_step_id(2)
    body = {"substrate": lattice_substrate(400, 2), "steps": anchored("between", width=100)}
    plan = {"factors": [{"step_id": litho, "field": "openings.width", "values": [100, 200]}]}
    assert preview_campaign(client, {**body, "plan": plan}).status_code == 200

    from spectre.plugins.structures import campaigns

    request = ProcessInput.model_validate(body)
    variant = campaigns.VariantPlan.model_validate(plan)
    indexes = campaigns.factor_step_indexes(variant, request.step_ids)
    _substrate, steps, _declared = campaigns.apply_combination(request.substrate, request.steps, {}, variant, indexes, [200], request.lattice_anchors)
    assert steps[1].openings == [(0, 100), (300, 500), (700, 800)]

    # un diamètre ne règle pas une ouverture entre les fils
    wrong = {"factors": [{"step_id": litho, "field": "openings.diameter", "values": [100, 200]}]}
    assert preview_campaign(client, {**body, "plan": wrong}).status_code == 422


# -- le pixel de N fils, par sa maille ---------------------------------------------------------------


@pytest.fixture
def simulated(monkeypatch) -> list[list[str]]:
    """Les étapes que StructureForge simule vraiment, appel par appel - sur un cache vide."""
    monkeypatch.setattr(simulation, "_checkpoints", OrderedDict())
    calls: list[list[str]] = []
    real = simulation.simulate

    def counting(geometry, steps, materials, recipes):
        calls.append([step.name for step in steps])
        return real(geometry, steps, materials, recipes)

    monkeypatch.setattr(simulation, "simulate", counting)
    return calls


def _pixel(wires: int, steps: list[dict] | None = None, run_id: str | None = None) -> simulation.SimulationResult:
    body = ProcessInput.model_validate({"substrate": lattice_substrate(400, wires), "steps": steps or sag_steps(100)})
    return simulation.simulate_process(body.substrate, body.steps, lattice_anchors=body.lattice_anchors, run_id=run_id)


def _tiled(polygon, pitch: float, wires: int):
    return shapely.union_all([translate(polygon, xoff=i * pitch) for i in range(wires)], grid_size=1e-6)


def test_a_pixel_of_several_wires_is_its_cell_repeated(simulated):
    one = _pixel(1)
    simulated.clear()
    three = _pixel(3)
    assert simulated == []  # la maille est celle de la vue « 1 fil », déjà connue : rien à simuler
    assert [frame.domain_width_nm for frame in three.frames] == [1200] * 4
    assert three.layer_origins == one.layer_origins
    for frame_one, frame_three in zip(one.frames, three.frames):
        assert [l.material for l in frame_three.layers] == [l.material for l in frame_one.layers]
        for layer_one, layer_three in zip(frame_one.layers, frame_three.layers):
            assert layer_three.polygon.symmetric_difference(_tiled(layer_one.polygon, 400, 3)).area < 1e-6
            assert layer_three.provenance == layer_one.provenance
    # le masque ouvert sur chaque fil : la résine en quatre morceaux
    resist = next(l for l in three.frames[2].layers if l.material == "Photoresist")
    assert len(resist.polygon.geoms) == 4

    # la maille d'un pixel inconnu se simule une fois ; le pixel, jamais
    simulation.clear_checkpoints()
    simulated.clear()
    five = _pixel(5)
    assert simulated == [[], ["Masque"], ["Litho SAG"], ["Couche"]]
    assert five.frames[-1].domain_width_nm == 2000 and five.frames[-1].layers[0].polygon.bounds[2] == 2000


def test_the_steps_that_see_the_whole_pixel_are_simulated_on_it(simulated):
    whole = {**lithography("Litho pixel", thickness_nm=50, openings=[[0, 1]]), "lattice_opening": {"mode": "pixel", "margin": 100}}
    steps = identified([*sag_steps(100), whole, etch("Gravure", depth_nm=5)])
    result = _pixel(3, steps)
    # la maille jusqu'à la couche, puis le pixel d'un bloc : l'ouverture sur tout le pixel et la gravure
    assert simulated == [[], ["Masque"], ["Litho SAG"], ["Couche"], ["Litho pixel"], ["Gravure"]]
    resists = [l for l in result.frames[4].layers if l.material == "Photoresist"]
    assert resists[-1].polygon.bounds[0] == 0 and resists[-1].polygon.bounds[2] == 1200
    assert len(resists[-1].polygon.geoms) == 2  # la marge de chaque côté du pixel
    simulated.clear()
    _pixel(3, steps)
    assert simulated == []  # les états répétés sont gardés comme les autres


def test_what_ends_the_cell():
    recipes = simulation.recipes_library()
    tilted_etch = next(name for name, recipe in recipes.etch.items() if recipe.angle_deg)
    tilted_deposition = next(name for name, recipe in recipes.deposition.items() if recipe.angle_deg)
    vertical_etch = next(name for name, recipe in recipes.etch.items() if recipe.mode.value == "directional" and not recipe.angle_deg)

    def prefix(steps: list[dict], wires: int = 3) -> int:
        body = ProcessInput.model_validate({"substrate": lattice_substrate(400, wires), "steps": steps})
        return simulation.periodic_prefix(body.substrate, body.steps, recipes, body.lattice_anchors)

    sag = sag_steps(100)
    assert prefix(sag) == 3
    assert prefix(sag, wires=1) == 0  # un fil : rien à répéter
    assert prefix([*sag, etch("RIE", recipe=vertical_etch, depth_nm=5), etch("Inclinée", recipe=tilted_etch, depth_nm=5)]) == 4
    assert prefix([*sag, deposition("Oblique", "SiO2", recipe=tilted_deposition, thickness_nm=5)]) == 3
    assert prefix([*sag, lithography("Absolue", thickness_nm=50, openings=[[10, 20]])]) == 3
    assert prefix(anchored("pixel", margin=100)) == 0  # avant l'ouverture sur tout le pixel, pas de motif
    assert prefix(anchored("between", width=100)) == 3
    semi_polar = {"kind": "epitaxial_growth", "name": "Semi-polaire", "material": "GaN", "thickness": length(10), "orientation": "semi_polar", "angle_deg": 30}
    assert prefix([*sag, semi_polar, deposition("Après", thickness_nm=5)]) == 3
    assert prefix([deposition("Seule", thickness_nm=5), lithography("Absolue", thickness_nm=50, openings=[[10, 20]])]) == 0  # pas de motif


def test_a_followed_pixel_counts_its_cell_steps_as_done_then_as_resumed(simulated):
    _pixel(3, run_id="run-pixel-0001")
    run = simulation.run_progress("run-pixel-0001")
    assert (run.state, run.total, run.done, run.resumed) == ("done", 3, 3, 0)
    _pixel(3, run_id="run-pixel-0002")
    run = simulation.run_progress("run-pixel-0002")
    assert (run.state, run.total, run.done, run.resumed) == ("done", 3, 3, 3)


def test_the_pixel_is_simulated_as_one_block_without_its_anchors(simulated):
    body = ProcessInput.model_validate({"substrate": lattice_substrate(400, 3), "steps": sag_steps(100)})
    result = simulation.simulate_process(body.substrate, body.steps)
    assert simulated == [[], ["Masque"], ["Litho SAG"], ["Couche"]]
    assert result.frames[-1].domain_width_nm == 1200
