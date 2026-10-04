"""Les étiquettes regroupées par brique, l'unité des paramètres déclarés et les étiquettes très
longues (TODO § 3 ter) : les étapes étiquetées d'une même brique n'ont qu'une étiquette, celle de la
brique (son nom, une ligne par étape, une accolade sur les couches qu'elles ont créées) ; une étape
étiquetée hors brique garde la sienne ; l'unité d'un paramètre déclaré est un champ à part, l'ancienne
astuce ``unit=`` de l'obtention reste lue ; aucune étiquette ne sort du SVG."""

from __future__ import annotations

import re

from support.accounts import signup
from support.structures import deposition, etch, label_texts, layer_label, lithography, simulate, substrate

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


def _brackets(svg: str) -> list[tuple[float, float, float]]:
    """``(x du trait vertical, y1, y2)`` de chaque accolade."""
    found = re.findall(r'class="sp-layer-bracket" data-y1="([\d.]+)" data-y2="([\d.]+)" data-x="([\d.]+)"', svg)
    return [(float(x), float(y1), float(y2)) for y1, y2, x in found]


def test_the_brackets_of_bricks_wrapped_around_each_other_stand_side_by_side(client):
    """Sur un pilier (un nanofil), les coquilles enveloppent le cœur : les hauteurs des briques se
    recouvrent. Chaque accolade a sa colonne, les étiquettes passent au-delà de la dernière ; deux
    briques empilées se partagent la même."""
    signup(client, "brick-columns@example.com")
    pillar = [
        deposition("Base", "GaN", recipe="MOCVD Epitaxial", thickness_nm=60),
        lithography("Masque", thickness_nm=40, openings=[(0.0, 70.0), (130.0, 200.0)]),
        etch("Gravure", depth_nm=60),
        {"kind": "resist_strip", "name": "Retrait", "material": "Photoresist"},
        deposition("Coquille 1", "SiO2", thickness_nm=8),
        deposition("Coquille 2", "Si3N4", thickness_nm=8),
        deposition("Coquille 3", "Al2O3", thickness_nm=8),
        deposition("Coquille 4", "SiO2", thickness_nm=8),
    ]
    bricks = [{"group_id": "a", "name": "Interne", "step_indexes": [4, 5]}, {"group_id": "b", "name": "Externe", "step_indexes": [6, 7]}]
    labels = {str(i): layer_label("", "thickness") for i in (0, 4, 5, 6, 7)}
    response = simulate(client, {"substrate": substrate(), "steps": pillar, "layer_labels": labels, "bricks": bricks})
    assert response.status_code == 200, response.text
    svg = response.json()["frames"][-1]["svg"]
    (x1, top1, bottom1), (x2, top2, bottom2) = _brackets(svg)
    assert top1 < bottom2 and top2 < bottom1  # les hauteurs se recouvrent
    assert abs(x1 - x2) >= 10  # deux colonnes
    # les traits des étiquettes ont leur coude au-delà de la dernière colonne, les textes plus loin encore
    elbows = [float(points.split()[1].split(",")[0]) for points in re.findall(r'<polyline points="([^"]+)"', svg)]
    assert min(elbows) > max(x1, x2)
    assert min(float(x) for x in re.findall(r'<text x="([\d.]+)"', svg)) > max(elbows)

    # deux briques empilées : une seule colonne
    stacked = _final_svg(
        client, layer_labels={str(i): layer_label("", "thickness") for i in range(4)},
        bricks=[{**ACTIVE, "group_id": "bas", "step_indexes": [0, 1]}, {**ACTIVE, "group_id": "haut", "name": "Contact", "step_indexes": [2, 3]}],
    )
    assert len({x for x, _y1, _y2 in _brackets(stacked)}) == 1 and len(_brackets(stacked)) == 2


def test_a_label_outside_ascii_stays_inside_the_svg(client):
    """Mesuré dans le navigateur (16 px, 600, police de l'application et ses replis) : « Œ » fait
    1.114 em, « 中 » 1 em, « 🔬 » 1.373 em - l'ancienne estimation (0.8 ou 0.7 em) les laissait
    sortir de 180 unités ; une lettre accentuée a la chasse de sa lettre de base (« é » : 0.59 em)."""
    signup(client, "wide-label@example.com")
    for text, em in (("Œ" * 40, 1.114), ("中" * 40, 1.0), ("🔬" * 20, 1.373), ("Ж" * 40, 0.923), ("é" * 40, 0.592)):
        svg = simulate(client, {"substrate": substrate(), "steps": [deposition("Oxyde")], "layer_labels": {"0": layer_label(text, "thickness")}}).json()["frames"][-1]["svg"]
        view_width = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))
        text_x = float(re.search(r'<g class="sp-layer-label"[^>]*>.*?<text x="([\d.]+)"', svg).group(1))
        assert text_x + len(text) * 16 * em <= view_width, (text, text_x, view_width)


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
