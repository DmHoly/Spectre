from __future__ import annotations

from types import SimpleNamespace

from spectre.core.versioning import (
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


def _exp(id_, process=None):
    return SimpleNamespace(id=id_, metadata={} if process is None else {"structureforge_process": process})


def test_branch_versions_progress_through_every_level():
    history = [
        _exp("a", _process([deposition("Oxyde")])),  # initial -> 1.0.0
        _exp("b", _process([deposition("Oxyde"), etch("Gravure")])),  # major -> 2.0.0
        _exp("c", _process([deposition("Oxyde", thickness_nm=99), etch("Gravure")])),  # minor -> 2.1.0
        _exp("d", _process([deposition("Oxyde renomme", thickness_nm=99), etch("Gravure")])),  # patch -> 2.1.1
        _exp("e", _process([deposition("Oxyde renomme", thickness_nm=99), etch("Gravure")])),  # none -> 2.1.1
    ]
    versions = compute_branch_versions(history)
    assert [versions[e.id]["version"] for e in history] == ["1.0.0", "2.0.0", "2.1.0", "2.1.1", "2.1.1"]
    assert [versions[e.id]["level"] for e in history] == ["initial", "major", "minor", "patch", "none"]


def test_a_commit_with_no_process_metadata_never_bumps():
    history = [_exp("a", _process([deposition("Oxyde")])), _exp("b", None)]
    versions = compute_branch_versions(history)
    assert versions["b"]["version"] == "1.0.0"
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
    assert versions["c"]["version"] == "2.0.0"


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
        ("1.0.0", "initial"),
        ("1.0.0", "none"),
        ("2.0.0", "major"),
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
