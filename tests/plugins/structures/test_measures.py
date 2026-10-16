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
