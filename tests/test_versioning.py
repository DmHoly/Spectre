from __future__ import annotations

from types import SimpleNamespace

from spectre.core.versioning import (
    classify_process_change,
    collapsed_dag,
    compute_branch_versions,
    determine_keep_ids,
)


def _process(steps, material="Si", width=200, thickness=50):
    return {
        "substrate": {"material": material, "domain_width": {"value": width, "unit": "nm"}, "thickness": {"value": thickness, "unit": "nm"}},
        "steps": steps,
    }


def _dep(name, material="SiO2", recipe="CVD Conformal", thickness=20):
    return {"kind": "deposition", "name": name, "material": material, "recipe": recipe, "thickness": {"value": thickness, "unit": "nm"}}


def _etch(name, recipe="Anisotropic RIE", depth=10):
    return {"kind": "etch", "name": name, "recipe": recipe, "depth": {"value": depth, "unit": "nm"}}


# -- classify_process_change --------------------------------------------------------------------


def test_no_baseline_is_initial():
    assert classify_process_change(None, _process([_dep("Oxyde")])) == "initial"


def test_identical_process_is_none():
    p = _process([_dep("Oxyde")])
    assert classify_process_change(p, p) == "none"
    assert classify_process_change(_process([_dep("Oxyde")]), _process([_dep("Oxyde")])) == "none"


def test_substrate_change_is_major():
    before = _process([_dep("Oxyde")], material="Si")
    after = _process([_dep("Oxyde")], material="Sapphire")
    assert classify_process_change(before, after) == "major"


def test_adding_a_step_is_major():
    before = _process([_dep("Oxyde")])
    after = _process([_dep("Oxyde"), _etch("Gravure")])
    assert classify_process_change(before, after) == "major"


def test_reordering_steps_of_different_kinds_is_major():
    before = _process([_dep("Oxyde"), _etch("Gravure")])
    after = _process([_etch("Gravure"), _dep("Oxyde")])
    assert classify_process_change(before, after) == "major"


def test_changing_a_real_field_is_minor():
    before = _process([_dep("Oxyde", thickness=20)])
    after = _process([_dep("Oxyde", thickness=40)])
    assert classify_process_change(before, after) == "minor"


def test_changing_a_recipe_is_minor():
    before = _process([_dep("Oxyde", recipe="CVD Conformal")])
    after = _process([_dep("Oxyde", recipe="ALD Conformal")])
    assert classify_process_change(before, after) == "minor"


def test_renaming_a_step_only_is_patch():
    before = _process([_dep("Oxyde initial")])
    after = _process([_dep("Oxyde renomme")])
    assert classify_process_change(before, after) == "patch"


def test_rename_plus_value_change_is_still_minor_not_patch():
    before = _process([_dep("Oxyde", thickness=20)])
    after = _process([_dep("Oxyde renomme", thickness=40)])
    assert classify_process_change(before, after) == "minor"


# -- compute_branch_versions ----------------------------------------------------------------------


def _exp(id_, process=None):
    return SimpleNamespace(id=id_, metadata={} if process is None else {"structureforge_process": process})


def test_branch_versions_progress_through_every_level():
    history = [
        _exp("a", _process([_dep("Oxyde")])),  # initial -> 1.0.0
        _exp("b", _process([_dep("Oxyde"), _etch("Gravure")])),  # major -> 2.0.0
        _exp("c", _process([_dep("Oxyde", thickness=99), _etch("Gravure")])),  # minor -> 2.1.0
        _exp("d", _process([_dep("Oxyde renomme", thickness=99), _etch("Gravure")])),  # patch -> 2.1.1
        _exp("e", _process([_dep("Oxyde renomme", thickness=99), _etch("Gravure")])),  # none -> 2.1.1
    ]
    versions = compute_branch_versions(history)
    assert [versions[e.id]["version"] for e in history] == ["1.0.0", "2.0.0", "2.1.0", "2.1.1", "2.1.1"]
    assert [versions[e.id]["level"] for e in history] == ["initial", "major", "minor", "patch", "none"]


def test_a_commit_with_no_process_metadata_never_bumps():
    history = [_exp("a", _process([_dep("Oxyde")])), _exp("b", None)]
    versions = compute_branch_versions(history)
    assert versions["b"]["version"] == "1.0.0"
    assert versions["b"]["level"] == "none"


def test_a_gap_with_no_process_does_not_reset_the_next_real_comparison():
    # a hypothetical commit carrying no process metadata must not be mistaken for "nothing to
    # compare against" (which would wrongly report the next real change as "initial")
    history = [
        _exp("a", _process([_dep("Oxyde")])),
        _exp("b", None),
        _exp("c", _process([_dep("Oxyde"), _etch("Gravure")])),
    ]
    versions = compute_branch_versions(history)
    assert versions["c"]["level"] == "major"
    assert versions["c"]["version"] == "2.0.0"


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
        "a": _process([_dep("Oxyde")]),
        "b": _process([_dep("Oxyde")]),
        "c": _process([_dep("Oxyde", thickness=99)]),
        "d": _process([_dep("Oxyde", thickness=99)]),
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
    processes = {"a": _process([_dep("Oxyde")]), "b": _process([_dep("Oxyde")]), "m": _process([_dep("Oxyde")])}
    keep = determine_keep_ids(dag, processes, tips=set())
    assert keep == {"a", "b", "m"}


def test_a_chain_of_several_collapsed_commits_reconnects_to_the_nearest_kept_ancestor():
    dag = {"a": [], "b": ["a"], "c": ["b"], "d": ["c"], "e": ["d"]}
    same = _process([_dep("Oxyde")])
    processes = {node: same for node in dag}
    keep = determine_keep_ids(dag, processes, tips={"e"})
    assert keep == {"a", "e"}  # only the root and the tip - nothing in between ever changed
    assert collapsed_dag(dag, keep) == {"a": [], "e": ["a"]}
