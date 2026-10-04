"""Les étiquettes de couches (TODO § 3 ter) : seules les étapes choisies en portent une, dessinée par
le serveur à droite de la structure et reliée à la couche que l'étape a créée - un texte (le
matériau par défaut) et, dessous, des valeurs de l'étape. La provenance des couches vient de la
simulation, pas d'un alignement de matériaux."""

from __future__ import annotations

import re

from support.accounts import signup
from support.structures import deposition, label_texts, layer_label, length, preview_campaign, simulate, substrate

STACK = [
    deposition("Tampon", "GaN", recipe="MOCVD Epitaxial", thickness_nm=2000),
    deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400),
    deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=3),
    deposition("p-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=150),
]
DOPING = {"3": [{"name": "dopage Mg", "value": 2e19, "obtention": {"unit": "cm-3"}}]}


def _final_svg(client, **body) -> str:
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": STACK, **body})
    assert response.status_code == 200, response.text
    return response.json()["frames"][-1]["svg"]


def _blocks(svg: str) -> list[tuple[float, float]]:
    """(haut, hauteur) de chaque étiquette dessinée."""
    return [(float(top), float(height)) for top, height in re.findall(r'class="sp-layer-label" data-top="([\d.]+)" data-height="([\d.]+)"', svg)]


def test_only_the_chosen_steps_carry_a_label_with_their_values(client):
    signup(client, "labels@example.com")
    svg = _final_svg(
        client,
        declared_params=DOPING,
        layer_labels={"2": layer_label("", "thickness", "composition"), "3": layer_label("p-GaN", "thickness", "declared:dopage Mg")},
    )
    # de haut en bas : p-GaN (dessus), puis le puits ; le texte vide prend le nom du matériau
    assert label_texts(svg) == ["p-GaN", "150 nm", "dopage Mg : 2e19 cm-3", "In0.20Ga0.80N", "3 nm", "In 20 %"]
    assert svg.count('class="sp-layer-label"') == 2
    # le dessin de StructureForge est gardé tel quel, à gauche, et la vue sans étiquettes est donnée
    assert svg.count("<path ") == 5 and 'data-bare-viewbox="0 0 ' in svg


def test_no_label_leaves_the_drawing_as_it_was(client):
    signup(client, "nolabels@example.com")
    svg = _final_svg(client)
    assert "sp-layer-labels" not in svg and svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5')


def test_a_value_the_step_does_not_have_is_left_out_and_lengths_read_in_a_readable_unit(client):
    signup(client, "values@example.com")
    svg = _final_svg(client, layer_labels={"0": layer_label("Tampon", "thickness", "composition", "declared:absent")})
    assert label_texts(svg) == ["Tampon", "2 µm"]


def test_each_frame_labels_the_layers_it_already_has_and_layers_name_their_step(client):
    signup(client, "frames@example.com")
    response = simulate(
        client,
        {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": STACK, "layer_labels": {"1": layer_label("n"), "3": layer_label("p")}},
    )
    frames = response.json()["frames"]
    assert [label_texts(frame["svg"]) for frame in frames] == [[], [], ["n"], ["n"], ["p", "n"]]
    # la provenance de chaque couche, calculée par le serveur (-1 : le substrat)
    assert [layer["step_index"] for layer in frames[-1]["layers"]] == [-1, 0, 1, 2, 3]


def test_a_flip_keeps_the_provenance_of_the_layers(client):
    signup(client, "flip@example.com")
    process_steps = [
        deposition("Métal avant", "Au", recipe="Evaporation (normal)", thickness_nm=20),
        {"kind": "flip", "name": "Retournement"},
        deposition("Métal arrière", "Ti", thickness_nm=10),
    ]
    frames = simulate(client, {"substrate": substrate(), "steps": process_steps, "layer_labels": {"0": layer_label("Or")}}).json()["frames"]
    after_flip = frames[2]["layers"]
    assert {layer["material"]: layer["step_index"] for layer in after_flip} == {"Au": 0, "Si": -1}
    assert {layer["material"]: layer["step_index"] for layer in frames[-1]["layers"]} == {"Au": 0, "Si": -1, "Ti": 2}
    assert label_texts(frames[-1]["svg"]) == ["Or"]


def test_ten_labelled_layers_are_stacked_without_overlap(client):
    signup(client, "ten@example.com")
    thin = [deposition(f"Couche {i}", "GaN" if i % 2 else "AlN", recipe="MOCVD Epitaxial", thickness_nm=2) for i in range(10)]
    labels = {str(i): layer_label(f"Couche {i}", "thickness") for i in range(10)}
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=500), "steps": thin, "layer_labels": labels})
    svg = response.json()["frames"][-1]["svg"]
    blocks = sorted(_blocks(svg))
    assert len(blocks) == 10
    for (top, height), (next_top, _) in zip(blocks, blocks[1:]):
        assert top + height <= next_top
    # toutes dans l'image
    width, height = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    assert blocks[0][0] >= 0 and blocks[-1][0] + blocks[-1][1] <= height


def test_the_label_text_is_escaped(client):
    signup(client, "escape@example.com")
    svg = _final_svg(client, declared_params={"3": [{"name": "<i>x</i>", "value": "<b>"}]}, layer_labels={"3": layer_label("<script>alert(1)</script>", "declared:<i>x</i>")})
    assert "<script>" not in svg and "<i>" not in svg and "<b>" not in svg
    assert label_texts(svg) == ["&lt;script&gt;alert(1)&lt;/script&gt;", "&lt;i&gt;x&lt;/i&gt; : &lt;b&gt;"]


def test_a_label_must_name_a_step_and_known_values(client):
    signup(client, "invalid@example.com")
    body = {"substrate": substrate(), "steps": STACK}
    response = simulate(client, {**body, "layer_labels": {"4": layer_label("hors")}})
    assert response.status_code == 422 and response.json()["code"] == "invalid_layer_label"
    assert simulate(client, {**body, "layer_labels": {"0": layer_label("x", "couleur")}}).status_code == 422
    assert simulate(client, {**body, "layer_labels": {"0": {"text": "x" * 41}}}).status_code == 422


def test_each_campaign_variant_writes_its_own_values(client):
    signup(client, "campaign-labels@example.com")
    process_steps = [{"id": "st_00000001", **deposition("Oxyde", thickness_nm=20)}]
    plan = {"factors": [{"step_id": "st_00000001", "field": "thickness", "values": [10, 2500]}]}
    response = preview_campaign(
        client, {"substrate": substrate(), "steps": process_steps, "plan": plan, "layer_labels": {"0": layer_label("Oxyde", "thickness")}}
    )
    assert response.status_code == 200, response.text
    assert [label_texts(svg) for svg in response.json()["svgs"]] == [["Oxyde", "10 nm"], ["Oxyde", "2.5 µm"]]


def test_lengths_keep_their_value_whatever_unit_they_were_given_in(client):
    signup(client, "units@example.com")
    process_steps = [{**deposition("Oxyde"), "thickness": length(1.25, "um")}]
    svg = simulate(client, {"substrate": substrate(), "steps": process_steps, "layer_labels": {"0": layer_label("", "thickness")}}).json()["frames"][-1]["svg"]
    assert label_texts(svg) == ["SiO2", "1.25 µm"]
