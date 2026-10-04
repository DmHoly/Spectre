"""Les étiquettes regroupées par brique, l'unité des paramètres déclarés et les étiquettes très
longues (TODO § 3 ter) : les étapes étiquetées d'une même brique n'ont qu'une étiquette, celle de la
brique (son nom, une ligne par étape, une accolade sur les couches qu'elles ont créées) ; une étape
étiquetée hors brique garde la sienne ; l'unité d'un paramètre déclaré est un champ à part, l'ancienne
astuce ``unit=`` de l'obtention reste lue ; aucune étiquette ne sort du SVG."""

from __future__ import annotations

import re

from support.accounts import signup
from support.structures import deposition, label_texts, layer_label, simulate, substrate

STACK = [
    deposition("n-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=400),
    deposition("Puits", "In0.20Ga0.80N", recipe="MOCVD Epitaxial", thickness_nm=30),
    deposition("p-GaN", "GaN", recipe="MOCVD Epitaxial", thickness_nm=120),
    deposition("Contact", "ITO", recipe="Sputter Metal (normal)", thickness_nm=100),
]
DOPING = {"2": [{"name": "dopage Mg", "value": 3e18, "unit": "cm⁻³"}]}
LABELS = {
    "1": layer_label("Puits", "thickness", "composition"),
    "2": layer_label("p-GaN", "thickness", "declared:dopage Mg"),
    "3": layer_label("ITO", "thickness"),
}
ACTIVE = {"group_id": "brick-zone", "name": "Zone active", "source": "b-001", "step_indexes": [1, 2]}


def _final_svg(client, **body) -> str:
    response = simulate(client, {"substrate": substrate("Sapphire", width_nm=1000, thickness_nm=300), "steps": STACK, **body})
    assert response.status_code == 200, response.text
    return response.json()["frames"][-1]["svg"]


def test_the_labelled_steps_of_a_brick_share_one_label_and_a_step_outside_keeps_its_own(client):
    signup(client, "brick-labels@example.com")
    svg = _final_svg(client, declared_params=DOPING, layer_labels=LABELS, bricks=[ACTIVE])
    # deux étiquettes : l'ITO (seul, hors brique, au-dessus) puis la brique - son nom, une ligne par étape
    assert svg.count('class="sp-layer-label"') == 2
    assert label_texts(svg) == ["ITO", "100 nm", "Zone active", "p-GaN : 120 nm · dopage Mg 3e18 cm⁻³", "Puits : 30 nm · In 20 %"]
    assert svg.count('data-grouped="true"') == 1 and svg.count('class="sp-layer-bracket"') == 1
    # sans brique, chaque étape a la sienne, comme avant
    assert _final_svg(client, declared_params=DOPING, layer_labels=LABELS).count('class="sp-layer-label"') == 3


def test_a_brick_with_a_single_labelled_step_keeps_the_label_of_that_step(client):
    signup(client, "brick-single@example.com")
    svg = _final_svg(client, layer_labels={"2": layer_label("p-GaN", "thickness")}, bricks=[ACTIVE])
    assert label_texts(svg) == ["p-GaN", "120 nm"] and "sp-layer-bracket" not in svg


def test_the_bracket_covers_the_layers_created_by_the_labelled_steps_of_the_brick():
    from spectre.plugins.structures import rendering, simulation
    from structureforge.process.steps import ProcessStep
    from pydantic import TypeAdapter

    steps = TypeAdapter(list[ProcessStep]).validate_python(STACK)
    spec = simulation.SubstrateSpec.model_validate(substrate("Sapphire", width_nm=1000, thickness_nm=300))
    result = simulation.simulate_process(spec, steps)
    frame, origins = result.frames[-1], result.layer_origins[-1]
    labels = {int(i): simulation.LayerLabel.model_validate(LABELS[i]) for i in ("1", "2")}
    brick = simulation.ProcessBrick.model_validate(ACTIVE)
    annotations = rendering.annotations_for(steps, {}, labels, origins, [brick])
    assert [(a.title, a.grouped) for a in annotations] == [("Zone active", True)]
    assert sorted(origins[k] for k in annotations[0].layers) == [1, 2]

    svg = rendering.labelled_svg(frame, {m.name: m.color for m in result.materials}, annotations)
    x, y, width, height, view = re.search(r'<svg x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" viewBox="([^"]+)"', svg).groups()
    vx, vy, vw, vh = (float(v) for v in view.split())
    scale = float(width) / vw

    def to_svg(geometry_y: float) -> float:
        return float(y) + (-geometry_y - vy) * scale

    ys = [point[1] for k in annotations[0].layers for ring in frame.layers[k].rings() for point in ring["exterior"]]
    y1, y2 = (float(v) for v in re.search(r'class="sp-layer-bracket" data-y1="([\d.]+)" data-y2="([\d.]+)"', svg).groups())
    # du haut du p-GaN au bas du puits : ni le n-GaN dessous, ni l'ITO dessus
    assert abs(y1 - to_svg(max(ys))) < 0.1 and abs(y2 - to_svg(min(ys))) < 0.1
    others = [point[1] for k, origin in enumerate(origins) if origin in (0, 3) for ring in frame.layers[k].rings() for point in ring["exterior"]]
    assert to_svg(max(others)) <= y1 - 0.1 or to_svg(min(others)) >= y2


def test_bricks_must_name_consecutive_steps_of_the_process(client):
    signup(client, "brick-invalid@example.com")
    body = {"substrate": substrate(), "steps": STACK}
    for bricks in (
        [{**ACTIVE, "step_indexes": [3, 4]}],  # hors du procédé
        [{**ACTIVE, "step_indexes": [0, 2]}],  # pas consécutives
        [ACTIVE, {**ACTIVE, "group_id": "autre", "step_indexes": [2, 3]}],  # une étape dans deux briques
        [ACTIVE, {**ACTIVE, "step_indexes": [3]}],  # deux fois le même groupe
    ):
        response = simulate(client, {**body, "bricks": bricks})
        assert response.status_code == 422 and response.json()["code"] == "invalid_brick", bricks
    for bad in ({**ACTIVE, "name": "  "}, {**ACTIVE, "group_id": "a b"}, {**ACTIVE, "step_indexes": []}, {**ACTIVE, "couleur": "x"}):
        assert simulate(client, {**body, "bricks": [bad]}).status_code == 422, bad


def test_a_declared_unit_is_a_field_and_the_former_obtention_trick_is_still_read(client):
    signup(client, "units-field@example.com")
    label = {"2": layer_label("p-GaN", "declared:dopage Mg")}
    with_field = _final_svg(client, declared_params={"2": [{"name": "dopage Mg", "value": 3e18, "unit": " cm⁻³ "}]}, layer_labels=label)
    assert label_texts(with_field) == ["p-GaN", "dopage Mg : 3e18 cm⁻³"]
    former = _final_svg(client, declared_params={"2": [{"name": "dopage Mg", "value": 3e18, "obtention": {"unit": "cm-3"}}]}, layer_labels=label)
    assert label_texts(former) == ["p-GaN", "dopage Mg : 3e18 cm-3"]
    # le champ l'emporte sur l'obtention ; trop longue, l'unité est refusée
    both = _final_svg(client, declared_params={"2": [{"name": "dopage Mg", "value": 3e18, "unit": "cm⁻³", "obtention": {"unit": "m-3"}}]}, layer_labels=label)
    assert label_texts(both)[1] == "dopage Mg : 3e18 cm⁻³"
    response = simulate(client, {"substrate": substrate(), "steps": STACK, "declared_params": {"2": [{"name": "x", "value": 1, "unit": "u" * 21}]}})
    assert response.status_code == 422


def test_a_declared_param_without_unit_keeps_its_former_shape():
    from spectre.plugins.structures.simulation import DeclaredParam

    assert DeclaredParam(name="dopage", value=1).model_dump() == {"name": "dopage", "value": 1, "obtention": {}}
    assert DeclaredParam(name="dopage", value=1, unit="  ").model_dump() == {"name": "dopage", "value": 1, "obtention": {}}
    assert DeclaredParam(name="dopage", value=1, unit="%").model_dump()["unit"] == "%"


def test_a_very_long_label_stays_inside_the_svg(client):
    """Mesuré dans le navigateur (DM Sans 600, 16 px) : 40 « W » font 641.6 unités, 1 em par lettre -
    l'ancienne estimation (0.58 em, colonne plafonnée à 320) laissait 307 unités hors du SVG."""
    signup(client, "long-label@example.com")
    process_steps = [deposition("Oxyde")]
    for text, measured in (("W" * 40, 641.6), ("M" * 40, 40 * 16 * 0.94)):
        svg = simulate(client, {"substrate": substrate(), "steps": process_steps, "layer_labels": {"0": layer_label(text, "thickness")}}).json()["frames"][-1]["svg"]
        view_width = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))
        text_x = float(re.search(r'<g class="sp-layer-label"[^>]*>.*?<text x="([\d.]+)"', svg).group(1))
        assert text_x + measured <= view_width, (text, text_x, view_width)
    # une ligne de valeurs très longue aussi (64 caractères au plus pour une ligne de brique, 48 sinon)
    declared = {"0": [{"name": "W" * 30, "value": "W" * 30}]}
    svg = simulate(
        client, {"substrate": substrate(), "steps": process_steps, "declared_params": declared, "layer_labels": {"0": layer_label("x", f"declared:{'W' * 30}")}}
    ).json()["frames"][-1]["svg"]
    line = label_texts(svg)[1]
    assert len(line) == 48 and line.endswith("…")
    view_width = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))
    text_x = float(re.search(r'<text x="([\d.]+)"[^>]*font-size="14"', svg).group(1))
    assert text_x + 47 * 14 * 1.0 <= view_width
