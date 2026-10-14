"""Le tableau d'une comparaison (``comparator.table.build``), sans HTTP : une ligne par structure,
une colonne par paramètre, et le code couleur de chaque cellule face à la base - rouge (modifié),
violet (paramètre ajouté), vert (couche en plus), orange (étape déplacée), absente."""

from __future__ import annotations

import copy

from spectre.plugins.comparator.table import Compared, build, comparable, differences
from support.comparator import cell, group
from support.structures import deposition, etch, fixed_step_id, length, substrate


def faceted(name: str, material: str, thickness_nm: float) -> dict:
    return {"kind": "faceted_growth", "name": name, "material": material, "thickness": length(thickness_nm), "rate_c": 1.0, "rate_m": 0.2, "rate_sp": 0.5, "semi_polar_angle_deg": 30.0, "seed_materials": ["GaN"]}


BASE_STEPS = [deposition("Masque", "Si3N4", thickness_nm=100), etch("Ouverture", depth_nm=100), faceted("GaN", "GaN", 1000), faceted("Puits", "In0.20Ga0.80N", 3)]
IDS = [fixed_step_id(i + 1) for i in range(len(BASE_STEPS))]


def process(steps: list[dict], **extra) -> dict:
    return {"substrate": substrate("GaN", width_nm=2000), "steps": copy.deepcopy(steps), **extra}


def row(label: str, steps: list[dict], ids: list[str] | None = None, **extra) -> Compared:
    return Compared(label, "study", label, process=process(steps, **extra), step_ids=list(ids or []))


def test_the_baseline_is_the_reference_and_a_changed_value_is_red():
    thicker = copy.deepcopy(BASE_STEPS)
    thicker[0]["thickness"] = length(120)
    table = build([row("A", BASE_STEPS, IDS), row("B", thicker, IDS)])

    assert [g["label"] for g in table["groups"]] == ["Substrat", "Masque", "Ouverture", "GaN", "Puits"]
    assert table["rows"][0]["baseline"] and not table["rows"][1]["baseline"]
    assert cell(table, 0, "Masque", "Épaisseur") == {"text": "100 nm", "status": "same", "title": ""}
    changed = cell(table, 1, "Masque", "Épaisseur")
    assert (changed["text"], changed["status"]) == ("120 nm", "changed")
    assert "base : 100 nm" in changed["title"]
    assert cell(table, 1, "Masque", "Matériau")["status"] == "same"
    assert table["summary"]["changed"] == 1
    assert table["rows"][1]["summary"]["changed"] == 1
    # le filtre « seulement les différences » : la colonne modifiée, pas les autres
    masque = group(table, "Masque")
    assert [c["differs"] for c in masque["columns"]] == [False, False, True]
    assert not group(table, "Substrat")["differs"]


def test_the_same_length_written_in_another_unit_is_the_same():
    in_um = copy.deepcopy(BASE_STEPS)
    in_um[2]["thickness"] = length(1, "um")
    table = build([row("A", BASE_STEPS, IDS), row("B", in_um, IDS)])
    assert cell(table, 1, "GaN", "Épaisseur") == {"text": "1 µm", "status": "same", "title": ""}


def test_a_declared_parameter_added_is_a_purple_column():
    declared = {"2": [{"name": "Dopage", "value": 3e18, "unit": "cm⁻³", "obtention": {}}]}
    table = build([row("A", BASE_STEPS, IDS), row("B", BASE_STEPS, IDS, declared_params=declared)])
    column = next(c for c in group(table, "GaN")["columns"] if c["label"] == "Dopage")
    assert column["status"] == "added_param"
    assert cell(table, 1, "GaN", "Dopage")["status"] == "added_param"
    assert cell(table, 1, "GaN", "Dopage")["text"] == "3e18 cm⁻³"
    assert cell(table, 0, "GaN", "Dopage")["text"] == "—"
    assert table["summary"]["added_params"] == 1


def test_a_removed_parameter_is_a_change():
    declared = {"2": [{"name": "Dopage", "value": 3e18, "obtention": {}}]}
    table = build([row("A", BASE_STEPS, IDS, declared_params=declared), row("B", BASE_STEPS, IDS)])
    removed = cell(table, 1, "GaN", "Dopage")
    assert (removed["text"], removed["status"]) == ("—", "changed")
    assert "retiré" in removed["title"]


def test_an_added_layer_is_green_where_it_belongs():
    capped = [*BASE_STEPS[:3], faceted("Barrière", "GaN", 10), BASE_STEPS[3]]
    capped_ids = [*IDS[:3], fixed_step_id(9), IDS[3]]
    table = build([row("A", BASE_STEPS, IDS), row("B", capped, capped_ids)])

    assert [g["label"] for g in table["groups"]] == ["Substrat", "Masque", "Ouverture", "GaN", "Barrière", "Puits"]
    added = group(table, "Barrière")
    assert (added["status"], added["position"]) == ("added_layer", None)
    assert cell(table, 1, "Barrière", "Épaisseur")["status"] == "added_layer"
    assert cell(table, 0, "Barrière", "Épaisseur")["status"] == "empty"
    # les autres étapes restent appariées par leur id : rien d'autre ne change
    assert table["summary"] == {"changed": 0, "added_params": 0, "added_layers": 1, "moved_layers": 0, "absent_layers": 0}


def test_a_removed_layer_is_absent():
    table = build([row("A", BASE_STEPS, IDS), row("B", [BASE_STEPS[0], *BASE_STEPS[2:]], [IDS[0], *IDS[2:]])])
    assert cell(table, 1, "Ouverture", "Profondeur")["status"] == "absent"
    assert table["rows"][1]["summary"]["absent_layers"] == 1


def test_steps_in_another_order_are_orange():
    swapped = [BASE_STEPS[0], BASE_STEPS[1], BASE_STEPS[3], {**BASE_STEPS[2], "thickness": length(900)}]
    table = build([row("A", BASE_STEPS, IDS), row("B", swapped, [IDS[0], IDS[1], IDS[3], IDS[2]])])

    statuses = {g["label"]: g["status"] for g in table["groups"]}
    assert list(statuses.values()).count("moved") == 1
    moved_label = next(label for label, status in statuses.items() if status == "moved")
    moved = cell(table, 1, moved_label, "Matériau")
    assert moved["status"] == "moved" and "Étape déplacée" in moved["title"]
    # la croissance GaN a aussi changé d'épaisseur : déplacée et modifiée
    thickness = cell(table, 1, "GaN", "Épaisseur")
    if moved_label == "GaN":
        assert thickness["status"] == "moved" and thickness["changed"] is True
    else:
        assert thickness["status"] == "changed"
    assert table["summary"]["moved_layers"] == 1


def test_without_shared_ids_steps_pair_by_kind_and_material():
    # deux études lancées à part : aucun id commun ; un puits retiré, une barrière ajoutée au bout
    other = [BASE_STEPS[0], BASE_STEPS[1], {**BASE_STEPS[2], "thickness": length(800)}, faceted("Barrière", "AlN", 5)]
    table = build([row("A", BASE_STEPS), row("B", other)])
    assert cell(table, 1, "GaN", "Épaisseur")["status"] == "changed"  # la même couche, plus fine
    assert cell(table, 1, "Masque", "Épaisseur")["status"] == "same"
    # le puits InGaN et la barrière AlN : même type d'étape, appariés à la même place
    assert cell(table, 1, "Puits", "Matériau")["status"] == "changed"

    swapped = build([row("A", BASE_STEPS), row("B", [BASE_STEPS[0], BASE_STEPS[1], BASE_STEPS[3], BASE_STEPS[2]])])
    assert [g["status"] for g in swapped["groups"]].count("moved") == 1
    assert swapped["summary"]["changed"] == 0


def test_a_wire_lattice_compares_its_pitch_not_the_wires_shown():
    def sag(wires: int) -> dict:
        return {"material": "GaN", "domain_width": length(wires * 1000), "thickness": length(50), "lattice": {"pitch": 1000, "wires": wires}}

    one = Compared("A", "study", "A", process={"substrate": sag(1), "steps": [deposition()]})
    six = Compared("B", "study", "B", process={"substrate": sag(6), "steps": [deposition()]})
    table = build([one, six])
    labels = [c["label"] for c in group(table, "Substrat")["columns"]]
    assert labels == ["Matériau", "Épaisseur", "Pas du réseau"]
    assert table["summary"]["changed"] == 0


def test_an_own_recipe_redefined_is_a_change():
    def with_recipe(selectivity: float) -> dict:
        recipe = {"name": "Gravure HCl", "mode": "isotropic", "selectivity": {"GaN": selectivity}}
        return process([etch("Ouverture", recipe="Gravure HCl")], recipes={"etch": [recipe]})

    table = build([Compared("A", "study", "A", process=with_recipe(1.0)), Compared("B", "study", "B", process=with_recipe(5.0))])
    recipe = cell(table, 1, "Ouverture", "Recette")
    assert (recipe["text"], recipe["status"]) == ("Gravure HCl", "changed")


def test_a_step_without_parameter_still_shows():
    flip = [*BASE_STEPS, {"kind": "flip", "name": "Retournement"}]
    table = build([row("A", BASE_STEPS, IDS), row("B", flip, [*IDS, fixed_step_id(7)])])
    assert [c["key"] for c in group(table, "Retournement")["columns"]] == ["present"]
    assert cell(table, 1, "Retournement", "Présente")["status"] == "added_layer"


def test_rows_without_parameters_say_why():
    images = Compared("img", "study", "Coupe", structure_kind="images", note="Structure donnée en images.")
    broken = Compared("bad", "study", "Disparue", error="Version introuvable.")
    table = build([row("A", BASE_STEPS, IDS), images, broken])
    assert table["rows"][1]["cells"] is None and table["rows"][1]["note"] == "Structure donnée en images."
    assert table["rows"][2]["cells"] is None and table["rows"][2]["error"] == "Version introuvable."


def test_a_declared_split_compares_its_factors():
    lines = [
        Compared("d0", "study", "W1", structure_kind="declared", declared=(["Recuit", "Gaz"], ["600 °C", "N2"])),
        Compared("d1", "study", "W2", structure_kind="declared", declared=(["Recuit", "Gaz"], ["650 °C", "N2"])),
        Compared("d2", "study", "W3", structure_kind="declared", declared=(["Recuit", "Gaz", "Durée"], ["600 °C", "N2", "2 h"])),
    ]
    table = build(lines)
    assert [g["label"] for g in table["groups"]] == ["Split déclaré"]
    assert cell(table, 1, "Split déclaré", "Recuit")["status"] == "changed"
    assert cell(table, 2, "Split déclaré", "Durée")["status"] == "added_param"


def test_the_baseline_can_be_any_row():
    thicker = copy.deepcopy(BASE_STEPS)
    thicker[0]["thickness"] = length(120)
    table = build([row("A", BASE_STEPS, IDS), row("B", thicker, IDS)], baseline=1)
    assert table["baseline"] == 1 and table["rows"][1]["baseline"]
    assert cell(table, 0, "Masque", "Épaisseur")["status"] == "changed"
    assert cell(table, 1, "Masque", "Épaisseur")["status"] == "same"


def test_the_differences_of_a_row_are_listed_and_counted_like_its_summary():
    thicker = copy.deepcopy(BASE_STEPS)
    thicker[0]["thickness"] = length(120)
    capped = [*thicker[:3], faceted("Barrière", "GaN", 10), thicker[3]]
    capped_ids = [*IDS[:3], fixed_step_id(9), IDS[3]]
    declared = {"2": [{"name": "Dopage", "value": 3e18, "unit": "cm⁻³", "obtention": {}}]}
    table = build([row("A", BASE_STEPS, IDS), row("B", capped, capped_ids, declared_params=declared), row("C", [BASE_STEPS[0], *BASE_STEPS[2:]], [IDS[0], *IDS[2:]])])

    assert differences(table, 0) == []  # la base n'a pas de différence avec elle-même
    listed = differences(table, 1)
    assert {"kind": "changed", "step": "Masque", "parameter": "Épaisseur", "from": "100 nm", "to": "120 nm"} in listed
    assert {"kind": "added_param", "step": "GaN", "parameter": "Dopage", "from": None, "to": "3e18 cm⁻³"} in listed
    assert {"kind": "added_layer", "step": "Barrière", "parameter": None, "from": None, "to": None} in listed
    assert {"kind": "absent", "step": "Ouverture", "parameter": None, "from": None, "to": None} in differences(table, 2)
    for i in (1, 2):
        assert len(differences(table, i)) == sum(table["rows"][i]["summary"].values())


def test_a_moved_and_modified_layer_counts_twice_like_the_summary():
    swapped = [BASE_STEPS[0], BASE_STEPS[1], BASE_STEPS[3], {**BASE_STEPS[2], "thickness": length(900)}]
    table = build([row("A", BASE_STEPS, IDS), row("B", swapped, [IDS[0], IDS[1], IDS[3], IDS[2]])])
    listed = differences(table, 1)
    assert sorted(d["kind"] for d in listed) == ["changed", "moved"]
    assert len(listed) == sum(table["rows"][1]["summary"].values())


def test_only_rows_with_the_same_kind_of_columns_are_comparable():
    process_row = row("A", BASE_STEPS, IDS)
    other = row("B", BASE_STEPS, IDS)
    split = Compared("d", "study", "W1", structure_kind="declared", declared=(["Recuit"], ["600 °C"]))
    split_too = Compared("e", "study", "W2", structure_kind="declared", declared=(["Recuit"], ["650 °C"]))
    images = Compared("img", "study", "Coupe", structure_kind="images", note="Structure donnée en images.")
    broken = Compared("bad", "study", "Disparue", error="Version introuvable.")
    assert comparable(process_row, other) and comparable(split, split_too)
    assert not comparable(process_row, split) and not comparable(split, process_row)
    assert not comparable(process_row, images) and not comparable(process_row, broken)
