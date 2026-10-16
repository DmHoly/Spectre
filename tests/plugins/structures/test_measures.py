"""Les cotes et les marques après un retournement : une étape peut porter des cotes (l'épaisseur ou
la largeur de ce qui est sous un point de son image), dessinées sur l'image de cette étape seulement,
avec ou sans étiquette ; une marque d'interface ne paraît qu'après son étape, et suit le retournement
de la plaque (sa surface passe dessous) ; déplacer une étiquette ne redessine que les images où elle
paraît."""

from __future__ import annotations

import re

from pydantic import TypeAdapter
from structureforge.process.steps import ProcessStep

from support.accounts import signup
from support.structures import deposition, layer_label, simulate, substrate

CLEAN = {"kind": "chemical", "name": "Clean HF", "description": "bain HF", "parameters": {}}
FLIP = {"kind": "flip", "name": "Retournement"}
STACK = [
    deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200),
    CLEAN,
    deposition("AlN", "AlN", recipe="MOCVD Epitaxial", thickness_nm=50),
]
_LENGTH_RE = re.compile(r'class="sp-measure" data-direction="(\w+)" data-step="(\d+)" data-measure="(\d+)" data-length="([^"]+)"')


def _frames(client, steps=STACK, **body) -> list[dict]:
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=400, thickness_nm=100), "steps": steps, **body})
    assert response.status_code == 200, response.text
    return response.json()["frames"]


def _measured(svg: str) -> list[tuple[str, int, float]]:
    return [(direction, int(step), float(length)) for direction, step, _k, length in _LENGTH_RE.findall(svg)]


def _simulated(steps: list[dict]):
    from spectre.plugins.structures import simulation

    process = TypeAdapter(list[ProcessStep]).validate_python(steps)
    spec = simulation.SubstrateSpec.model_validate(substrate("Sapphire", width_nm=400, thickness_nm=100))
    return process, simulation.simulate_process(spec, process)


def test_a_measure_is_drawn_on_its_step_image_only_with_its_length(client):
    signup(client, "measure-thickness@example.com")
    measures = [{"direction": "thickness", "point": [100, 100]}, {"direction": "width", "point": [100, 100]}]
    frames = _frames(client, layer_labels={"0": {"shown": False, "measures": measures}})
    # l'image après l'étape 1 (le GaN) : son épaisseur et sa largeur, rien d'autre (pas d'étiquette)
    assert _measured(frames[1]["svg"]) == [("thickness", 0, 200.0), ("width", 0, 400.0)]
    assert 'class="sp-layer-label"' not in frames[1]["svg"]
    assert all("sp-measure" not in frame["svg"] for k, frame in enumerate(frames) if k != 1)


def test_a_measure_takes_the_whole_material_or_the_clicked_layer_alone(client):
    signup(client, "measure-scope@example.com")
    steps = [deposition("GaN 1", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200), deposition("GaN 2", "GaN", recipe="MOCVD Epitaxial", thickness_nm=100)]
    measures = [{"direction": "thickness", "point": [100, 250]}, {"direction": "thickness", "point": [100, 250], "scope": "layer"}]
    frames = _frames(client, steps=steps, layer_labels={"1": {"text": "GaN 2", "measures": measures}})
    assert _measured(frames[2]["svg"]) == [("thickness", 1, 300.0), ("thickness", 1, 100.0)]
    # l'étiquette est là aussi, et seule sur l'image d'avant (la couche n'y est pas encore : rien)
    assert 'class="sp-layer-label"' in frames[2]["svg"] and "sp-measure" not in frames[1]["svg"]


def test_measures_and_a_measure_only_label_do_not_count_as_a_label_change():
    from spectre.plugins.structures.simulation import LayerLabel, label_without_place

    only = LayerLabel(shown=False, measures=[{"direction": "width", "point": [1.234, 2]}])
    assert only.model_dump(mode="json") == {"text": "", "values": [], "measures": [{"direction": "width", "point": [1.2, 2.0], "scope": "material"}], "shown": False}
    assert label_without_place(only.model_dump(mode="json")) is None
    labelled = LayerLabel(text="p", values=["thickness"], measures=[{"direction": "thickness", "point": [0, 0]}])
    assert label_without_place(labelled.model_dump(mode="json")) == {"text": "p", "values": ["thickness"]}
    # une étiquette sans cote s'enregistre comme avant les cotes
    assert LayerLabel(text="p").model_dump(mode="json") == {"text": "p", "values": []}


def test_a_mark_is_drawn_only_once_its_step_has_happened(client):
    signup(client, "mark-after-step@example.com")
    frames = _frames(client, layer_labels={"1": layer_label("Clean")})
    assert [frame["svg"].count('data-interface="true"') for frame in frames] == [0, 0, 1, 1]


def test_after_a_flip_a_mark_points_at_its_interface_now_underneath():
    from spectre.plugins.structures import rendering, simulation

    steps, result = _simulated([*STACK, FLIP])
    frame, origins = result.frames[-1], result.layer_origins[-1]
    (mark,) = rendering.annotations_for(steps, {}, {1: simulation.LayerLabel(text="Clean")}, origins)
    assert mark.interface and mark.flipped
    _x, y = rendering._interface_anchor(frame, mark.layers, mark.after, mark.flipped)
    # l'AlN, déposé après le nettoyage, est maintenant dessous : la marque est sur son dessus
    (aln,) = [layer for layer, origin in zip(frame.layers, origins) if origin == 2]
    assert abs(y - aln.polygon.bounds[3]) < 1
    # avant le retournement, la même marque est sur le dessus du GaN
    (before,) = rendering.annotations_for(steps, {}, {1: simulation.LayerLabel(text="Clean")}, result.layer_origins[3], through=3)
    assert not before.flipped
    assert abs(rendering._interface_anchor(result.frames[3], before.layers, before.after)[1] - 200) < 1


def test_moving_a_label_redraws_only_the_images_it_is_on(monkeypatch):
    from spectre.plugins.structures import rendering, simulation

    steps, result = _simulated(STACK)
    drawn: list[int] = []
    draw = rendering.labelled_svg
    monkeypatch.setattr(rendering, "labelled_svg", lambda frame, *a, **k: drawn.append(frame.step_index) or draw(frame, *a, **k))

    def payload(offset):
        labels = {0: simulation.LayerLabel(text="GaN"), 2: simulation.LayerLabel(text="AlN", offset=offset)}
        return rendering.frames_payload(result.frames, result.materials, result.layer_origins, steps, {}, labels, [], result.frame_keys)

    payload(None)
    drawn.clear()
    moved = payload((10, 20))
    # l'AlN n'est que sur la dernière image : elle seule est redessinée, les autres sont reprises
    assert drawn == [3] and 'data-offset="10 20"' in moved["frames"][3]["svg"]


def _followed(svg: str) -> list[tuple[int, int, float, float]]:
    """Les cotes suivies d'une image : (étape de la cote, étape de l'image, longueur, longueur d'origine)."""
    found = re.findall(r'class="sp-measure"[^>]*data-step="(\d+)" data-measure="\d+" data-at="(\d+)" data-length="([^"]+)"[^>]*data-reference="([^"]+)"', svg)
    return [(int(step), int(at), float(length), float(reference)) for step, at, length, reference in found]


def test_a_measure_followed_at_a_later_step_measures_the_same_layer_there_with_its_change(client):
    from support.structures import fixed_step_id, identified

    signup(client, "measure-followed@example.com")
    planarize = {"kind": "planarization", "name": "Planarisation", "target_level": {"value": 300, "unit": "nm"}}
    steps = identified([deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400), CLEAN, planarize])
    measure = {"direction": "thickness", "point": [100, 200], "also": [fixed_step_id(3), "st_ffffffff"]}
    frames = _frames(client, steps=steps, layer_labels={"0": {"shown": False, "measures": [measure]}})
    assert _measured(frames[1]["svg"]) == [("thickness", 0, 400.0)]
    # pas sur l'image du nettoyage (non suivie) ; après la planarisation à 300 nm : 300 nm, 100 nm de moins
    assert "sp-measure" not in frames[2]["svg"]
    assert _followed(frames[3]["svg"]) == [(0, 2, 300.0, 400.0)]
    assert "300 nm (−100 nm)" in frames[3]["svg"]


def test_a_followed_measure_finds_its_layer_again_after_a_flip():
    from spectre.plugins.structures import rendering, simulation

    steps, result = _simulated([*STACK, FLIP])
    measure = simulation.Measure(direction="thickness", point=(100, 100), scope="layer")
    line = rendering.followed_measure_line(result.frames, result.layer_origins, steps, measure, 0, 0, 3)
    (gan,) = [layer for layer, origin in zip(result.frames[-1].layers, result.layer_origins[-1]) if origin == 0]
    # le GaN retourné : toujours 200 nm, mesuré là où il est maintenant
    assert line is not None and line.length == 200.0 and line.reference == 200.0
    assert gan.polygon.bounds[1] - 1e-6 <= min(line.y1, line.y2) and max(line.y1, line.y2) <= gan.polygon.bounds[3] + 1e-6


def test_a_measure_names_the_later_steps_it_follows_by_their_ids():
    import pytest
    from pydantic import ValidationError

    from spectre.plugins.structures.simulation import Measure

    assert Measure(direction="width", point=(0, 0)).model_dump(mode="json") == {"direction": "width", "point": [0.0, 0.0], "scope": "material"}
    assert Measure(direction="width", point=(0, 0), also=["st_00000002", "st_00000002"]).also == ["st_00000002"]
    with pytest.raises(ValidationError):
        Measure(direction="width", point=(0, 0), also=["étape 2"])


def _substrate_with(measures: list[dict]) -> dict:
    return {**substrate("Sapphire", width_nm=400, thickness_nm=100), "measures": measures}


def test_a_substrate_measure_is_drawn_on_the_first_image_and_followed_like_a_layers(client):
    from support.structures import fixed_step_id, identified

    signup(client, "measure-substrate@example.com")
    planarize = {"kind": "planarization", "name": "Planarisation", "target_level": {"value": 300, "unit": "nm"}}
    steps = identified([deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400), CLEAN, planarize])
    measure = {"direction": "thickness", "point": [100, -50], "also": [fixed_step_id(3)]}
    response = simulate(client, {"substrate": _substrate_with([measure]), "steps": steps})
    assert response.status_code == 200, response.text
    frames = response.json()["frames"]
    # sur l'image de départ : l'épaisseur du substrat, étape -1
    assert re.findall(r'class="sp-measure" data-direction="(\w+)" data-step="(-1)" data-measure="0" data-length="([^"]+)"', frames[0]["svg"]) == [("thickness", "-1", "100")]
    # pas sur celles d'après, sauf où elle est suivie : après la planarisation, toujours 100 nm
    assert all("sp-measure" not in frames[k]["svg"] for k in (1, 2))
    assert re.findall(r'data-step="(-?\d+)" data-measure="\d+" data-at="(\d+)" data-length="([^"]+)"', frames[3]["svg"]) == [("-1", "2", "100")]
    assert "100 nm (=)" in frames[3]["svg"]


def test_substrate_measures_neither_change_the_version_nor_the_simulation():
    from spectre.plugins.experiments.versioning import classify_process_change, structure_signature
    from spectre.plugins.structures import simulation

    plain = simulation.SubstrateSpec.model_validate(substrate("Sapphire", width_nm=400, thickness_nm=100))
    measured = simulation.SubstrateSpec.model_validate(_substrate_with([{"direction": "width", "point": [1.234, -2]}]))
    # un substrat sans cote s'enregistre comme avant ; avec, sa cote est gardée
    assert "measures" not in plain.model_dump(mode="json")
    assert measured.model_dump(mode="json")["measures"] == [{"direction": "width", "point": [1.2, -2.0], "scope": "material"}]
    process = lambda spec: {"structureforge_process": simulation.process_metadata(spec, [], {}, None)}
    assert classify_process_change(structure_signature(process(plain)), structure_signature(process(measured))) == "none"
    # la simulation (sa clé de reprise) ne voit pas non plus les cotes
    assert simulation._checkpoint_keys(plain, [], simulation.RecipeLibrary()) == simulation._checkpoint_keys(measured, [], simulation.RecipeLibrary())
