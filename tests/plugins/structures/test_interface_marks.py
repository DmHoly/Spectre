"""Les marques d'interface : une étape qui ne crée pas de couche (un nettoyage, une gravure, un etch
back) peut porter une étiquette, dessinée comme une marque reliée en pointillé à la surface telle
qu'elle était quand l'étape a eu lieu - entre les couches d'avant et celles d'après ; jamais groupée
avec l'étiquette d'une brique ; sa profondeur (une gravure) et ses paramètres déclarés écrits dessous."""

from __future__ import annotations

from pydantic import TypeAdapter
from structureforge.process.steps import ProcessStep

from support.accounts import signup
from support.structures import deposition, etch, label_texts, layer_label, simulate, substrate

CLEAN = {"kind": "chemical", "name": "Clean HF", "description": "bain HF", "parameters": {}}
STACK = [
    deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200),
    CLEAN,
    deposition("AlN", "AlN", recipe="MOCVD Epitaxial", thickness_nm=50),
]
DURATION = {"1": [{"name": "durée", "value": 30, "unit": "s"}]}


def _final_svg(client, steps=STACK, **body) -> str:
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=400, thickness_nm=100), "steps": steps, **body})
    assert response.status_code == 200, response.text
    return response.json()["frames"][-1]["svg"]


def test_a_step_without_a_layer_is_marked_at_the_interface_it_happened_on(client):
    signup(client, "interface-mark@example.com")
    svg = _final_svg(client, declared_params=DURATION, layer_labels={"1": layer_label("", "declared:durée")})
    assert svg.count('data-interface="true"') == 1 and 'stroke-dasharray="4 3"' in svg
    # le texte vide prend le nom de l'étape (pas un matériau), ses paramètres déclarés dessous
    assert label_texts(svg) == ["Clean HF", "durée : 30 s"]


def test_the_mark_points_at_the_surface_between_the_layers_before_and_after():
    from spectre.plugins.structures import rendering, simulation

    steps = TypeAdapter(list[ProcessStep]).validate_python(STACK)
    spec = simulation.SubstrateSpec.model_validate(substrate("Sapphire", width_nm=400, thickness_nm=100))
    result = simulation.simulate_process(spec, steps)
    frame, origins = result.frames[-1], result.layer_origins[-1]
    annotations = rendering.annotations_for(steps, {}, {1: simulation.LayerLabel(text="Clean")}, origins)
    assert len(annotations) == 1 and annotations[0].interface
    mark = annotations[0]
    assert sorted(origins[k] for k in mark.layers) == [simulation.SUBSTRATE_ORIGIN, 0]
    assert [origins[k] for k in mark.after] == [2]
    _x, y = rendering._interface_anchor(frame, mark.layers, mark.after)
    # le haut du GaN (200 nm sur le saphir, dont le dessus est à 0), là où l'AlN est posé
    assert abs(y - 200) < 1


def test_an_etch_mark_writes_its_depth_and_is_never_grouped_with_its_brick(client):
    signup(client, "interface-etch@example.com")
    steps = [deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200), etch("Etch back", recipe="Anisotropic RIE", depth_nm=40)]
    labels = {"0": layer_label("GaN", "thickness"), "1": layer_label("", "depth")}
    brick = {"group_id": "b1", "name": "Croissance + etch back", "step_indexes": [0, 1]}
    svg = _final_svg(client, steps=steps, layer_labels=labels, bricks=[brick])
    # deux étiquettes à part : celle du GaN (la brique n'a qu'une couche étiquetée) et la marque
    assert "sp-layer-bracket" not in svg and svg.count('data-interface="true"') == 1
    assert label_texts(svg) == ["Etch back", "40 nm", "GaN", "200 nm"]


def test_a_mark_with_nothing_on_it_points_at_the_bare_surface(client):
    signup(client, "interface-bare@example.com")
    steps = [deposition("GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=200), CLEAN]
    svg = _final_svg(client, steps=steps, layer_labels={"1": layer_label("Clean final")})
    assert svg.count('data-interface="true"') == 1 and label_texts(svg) == ["Clean final"]
