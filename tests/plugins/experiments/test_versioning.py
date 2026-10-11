from __future__ import annotations

from types import SimpleNamespace

from spectre.plugins.experiments.versioning import (
    classify_process_change,
    collapsed_dag,
    compute_branch_versions,
    determine_keep_ids,
    structure_signature,
)

from support.structures import deposition, etch, substrate


def _process(steps, material="Si", width=200, thickness=50):
    return {"substrate": substrate(material, width_nm=width, thickness_nm=thickness), "steps": steps}


# -- classify_process_change --------------------------------------------------------------------


def test_no_baseline_is_initial():
    assert classify_process_change(None, _process([deposition("Oxyde")])) == "initial"


def test_identical_process_is_none():
    p = _process([deposition("Oxyde")])
    assert classify_process_change(p, p) == "none"
    assert classify_process_change(_process([deposition("Oxyde")]), _process([deposition("Oxyde")])) == "none"


def test_substrate_change_is_major():
    before = _process([deposition("Oxyde")], material="Si")
    after = _process([deposition("Oxyde")], material="Sapphire")
    assert classify_process_change(before, after) == "major"


def test_adding_a_step_is_major():
    before = _process([deposition("Oxyde")])
    after = _process([deposition("Oxyde"), etch("Gravure")])
    assert classify_process_change(before, after) == "major"


def test_reordering_steps_of_different_kinds_is_major():
    before = _process([deposition("Oxyde"), etch("Gravure")])
    after = _process([etch("Gravure"), deposition("Oxyde")])
    assert classify_process_change(before, after) == "major"


def test_removing_a_step_is_major():
    before = _process([deposition("Oxyde"), etch("Gravure")])
    assert classify_process_change(before, _process([deposition("Oxyde")])) == "major"


def test_swapping_two_steps_of_the_same_kind_is_major_when_their_ids_say_so():
    """Deux dépôts échangés gardent la même suite de types : sans ids, un réglage à chaque
    position (mineur) ; avec les ids des étapes, la même étape a changé de place (majeur)."""
    before = _process([deposition("Oxyde"), deposition("Nitrure", "Si3N4")])
    after = _process([deposition("Nitrure", "Si3N4"), deposition("Oxyde")])
    assert classify_process_change(before, after) == "minor"
    assert classify_process_change(before, after, before_step_ids=["st_a", "st_b"], after_step_ids=["st_b", "st_a"]) == "major"
    # le même procédé, les mêmes ids dans le même ordre : rien
    assert classify_process_change(before, before, before_step_ids=["st_a", "st_b"], after_step_ids=["st_a", "st_b"]) == "none"


def test_a_step_replaced_by_another_of_the_same_kind_is_major():
    before = _process([deposition("Oxyde"), deposition("Nitrure", "Si3N4")])
    after = _process([deposition("Oxyde"), deposition("Alumine", "Al2O3")])
    # réglée en place (le même id) : un matériau, un paramètre - mineur ; retirée puis une autre
    # ajoutée à sa place (un autre id) : une couche retirée et une ajoutée - majeur
    assert classify_process_change(before, after, before_step_ids=["st_a", "st_b"], after_step_ids=["st_a", "st_b"]) == "minor"
    assert classify_process_change(before, after, before_step_ids=["st_a", "st_b"], after_step_ids=["st_a", "st_c"]) == "major"


def test_two_processes_without_a_common_step_id_compare_by_shape():
    """Deux études lancées à part (ou une étude publiée dans la référence d'une autre) n'ont aucun
    id commun : leurs ids ne disent rien, la suite des types et les réglages décident."""
    p = _process([deposition("Oxyde"), deposition("Nitrure", "Si3N4")])
    assert classify_process_change(p, p, before_step_ids=["st_a", "st_b"], after_step_ids=["st_x", "st_y"]) == "none"
    thicker = _process([deposition("Oxyde"), deposition("Nitrure", "Si3N4", thickness_nm=80)])
    assert classify_process_change(p, thicker, before_step_ids=["st_a", "st_b"], after_step_ids=["st_x", "st_y"]) == "minor"


def test_changing_a_real_field_is_minor():
    before = _process([deposition("Oxyde", thickness_nm=20)])
    after = _process([deposition("Oxyde", thickness_nm=40)])
    assert classify_process_change(before, after) == "minor"


def test_changing_a_recipe_is_minor():
    before = _process([deposition("Oxyde", recipe="CVD Conformal")])
    after = _process([deposition("Oxyde", recipe="ALD Conformal")])
    assert classify_process_change(before, after) == "minor"


def test_renaming_a_step_only_is_patch():
    before = _process([deposition("Oxyde initial")])
    after = _process([deposition("Oxyde renomme")])
    assert classify_process_change(before, after) == "patch"


def test_rename_plus_value_change_is_still_minor_not_patch():
    before = _process([deposition("Oxyde", thickness_nm=20)])
    after = _process([deposition("Oxyde renomme", thickness_nm=40)])
    assert classify_process_change(before, after) == "minor"


# -- compute_branch_versions ----------------------------------------------------------------------


def _exp(id_, process=None, step_ids=None):
    metadata = {} if process is None else {"structureforge_process": process}
    if step_ids is not None:
        metadata["process_step_ids"] = step_ids
    return SimpleNamespace(id=id_, metadata=metadata)


def test_branch_versions_progress_through_every_level():
    history = [
        _exp("a", _process([deposition("Oxyde")])),  # initial -> 1.0
        _exp("b", _process([deposition("Oxyde"), etch("Gravure")])),  # major -> 2.0
        _exp("c", _process([deposition("Oxyde", thickness_nm=99), etch("Gravure")])),  # minor -> 2.1
        _exp("d", _process([deposition("Oxyde renomme", thickness_nm=99), etch("Gravure")])),  # patch -> 2.1
        _exp("e", _process([deposition("Oxyde renomme", thickness_nm=99), etch("Gravure")])),  # none -> 2.1
    ]
    versions = compute_branch_versions(history)
    assert [versions[e.id]["version"] for e in history] == ["1.0", "2.0", "2.1", "2.1", "2.1"]
    assert [versions[e.id]["level"] for e in history] == ["initial", "major", "minor", "patch", "none"]


def test_a_commit_with_no_process_metadata_never_bumps():
    history = [_exp("a", _process([deposition("Oxyde")])), _exp("b", None)]
    versions = compute_branch_versions(history)
    assert versions["b"]["version"] == "1.0"
    assert versions["b"]["level"] == "none"


def test_a_gap_with_no_process_does_not_reset_the_next_real_comparison():
    # a hypothetical commit carrying no process metadata must not be mistaken for "nothing to
    # compare against" (which would wrongly report the next real change as "initial")
    history = [
        _exp("a", _process([deposition("Oxyde")])),
        _exp("b", None),
        _exp("c", _process([deposition("Oxyde"), etch("Gravure")])),
    ]
    versions = compute_branch_versions(history)
    assert versions["c"]["level"] == "major"
    assert versions["c"]["version"] == "2.0"


def test_a_pictured_structure_is_versioned_by_its_revision_not_its_image():
    # structure en image : même révision (dessin remplacé) -> rien ; nouvelle révision -> majeur
    assert structure_signature({"structure_image_revision": "r1"}) == {"image_revision": "r1"}
    assert structure_signature({}) is None
    history = [
        SimpleNamespace(id="a", metadata={"structure_image_revision": "r1"}),
        SimpleNamespace(id="b", metadata={"structure_image_revision": "r1"}),
        SimpleNamespace(id="c", metadata={"structure_image_revision": "r2"}),
    ]
    versions = compute_branch_versions(history)
    assert [(versions[e.id]["version"], versions[e.id]["level"]) for e in history] == [
        ("1.0", "initial"),
        ("1.0", "none"),
        ("2.0", "major"),
    ]


def test_switching_between_drawn_and_pictured_is_major():
    drawn = _process([deposition("Oxyde")])
    assert classify_process_change(drawn, {"image_revision": "r1"}) == "major"
    assert classify_process_change({"image_revision": "r1"}, drawn) == "major"


# -- determine_keep_ids / collapsed_dag ------------------------------------------------------------


def test_collapsing_removes_only_non_bumping_single_parent_non_tip_commits():
    #   a (root, major/initial)
    #   |
    #   b (tag only, no process change)
    #   |
    #   c (thickness changed, minor)
    #   |
    #   d (tip, no process change)
    dag = {"a": [], "b": ["a"], "c": ["b"], "d": ["c"]}
    processes = {
        "a": _process([deposition("Oxyde")]),
        "b": _process([deposition("Oxyde")]),
        "c": _process([deposition("Oxyde", thickness_nm=99)]),
        "d": _process([deposition("Oxyde", thickness_nm=99)]),
    }
    keep = determine_keep_ids(dag, processes, tips={"d"})
    assert keep == {"a", "c", "d"}  # b collapsed: single-parent, not a tip, no process change

    collapsed = collapsed_dag(dag, keep)
    assert collapsed == {"a": [], "c": ["a"], "d": ["c"]}


def test_merges_and_roots_are_always_kept_even_without_a_process_change():
    #   a (root)      b (root)
    #    \            /
    #     m (merge, identical process to a - still kept)
    dag = {"a": [], "b": [], "m": ["a", "b"]}
    processes = {"a": _process([deposition("Oxyde")]), "b": _process([deposition("Oxyde")]), "m": _process([deposition("Oxyde")])}
    keep = determine_keep_ids(dag, processes, tips=set())
    assert keep == {"a", "b", "m"}


def test_a_chain_of_several_collapsed_commits_reconnects_to_the_nearest_kept_ancestor():
    dag = {"a": [], "b": ["a"], "c": ["b"], "d": ["c"], "e": ["d"]}
    same = _process([deposition("Oxyde")])
    processes = {node: same for node in dag}
    keep = determine_keep_ids(dag, processes, tips={"e"})
    assert keep == {"a", "e"}  # only the root and the tip - nothing in between ever changed
    assert collapsed_dag(dag, keep) == {"a": [], "e": ["a"]}


def test_changing_a_declared_parameter_is_minor():
    before = _process([deposition("PGaN")])
    after = {**_process([deposition("PGaN")]), "declared_params": {"0": [{"name": "dopage", "value": 1e19, "obtention": {}}]}}
    assert classify_process_change(before, after) == "minor"
    assert classify_process_change(after, after) == "none"


def test_two_levels_only_a_layer_is_major_a_setting_minor_a_retouche_keeps_the_number():
    """X.Y (2026-10-11) : une étape ajoutée est un majeur, un paramètre déclaré ajouté puis réglé
    sont des mineurs, un renommage (une retouche) garde le numéro - il n'y a plus de Z."""
    declared = {"0": [{"name": "dopage", "value": 1e19, "obtention": {}}]}
    history = [
        _exp("a", _process([deposition("PGaN")])),
        _exp("b", {**_process([deposition("PGaN")]), "declared_params": declared}),
        _exp("c", {**_process([deposition("PGaN")]), "declared_params": {"0": [{**declared["0"][0], "value": 5e19}]}}),
        _exp("d", {**_process([deposition("PGaN dopé")]), "declared_params": {"0": [{**declared["0"][0], "value": 5e19}]}}),
        _exp("e", {**_process([deposition("PGaN dopé"), etch("Gravure")]), "declared_params": {"0": [{**declared["0"][0], "value": 5e19}]}}),
    ]
    versions = compute_branch_versions(history)
    assert [(versions[e.id]["version"], versions[e.id]["level"]) for e in history] == [
        ("1.0", "initial"),
        ("1.1", "minor"),
        ("1.2", "minor"),
        ("1.2", "patch"),
        ("2.0", "major"),
    ]


def test_a_history_where_a_layer_moves_bumps_the_major():
    """Le long d'une piste, les ids d'étape suivent chaque étape : la déplacer est un majeur, même
    entre deux étapes du même type."""
    oxide_first = _process([deposition("Oxyde"), deposition("Nitrure", "Si3N4")])
    nitride_first = _process([deposition("Nitrure", "Si3N4"), deposition("Oxyde")])
    history = [
        _exp("a", oxide_first, ["st_a", "st_b"]),
        _exp("b", nitride_first, ["st_b", "st_a"]),  # les mêmes étapes, échangées
        _exp("c", nitride_first, ["st_b", "st_a"]),  # une étiquette : rien
    ]
    versions = compute_branch_versions(history)
    assert [(versions[e.id]["version"], versions[e.id]["level"]) for e in history] == [("1.0", "initial"), ("2.0", "major"), ("2.0", "none")]
    # le graphe réduit garde la version déplacée
    dag = {"a": [], "b": ["a"], "c": ["b"]}
    processes = {e.id: structure_signature(e.metadata) for e in history}
    step_ids = {e.id: e.metadata.get("process_step_ids") for e in history}
    assert determine_keep_ids(dag, processes, tips=set(), step_ids=step_ids) == {"a", "b"}

