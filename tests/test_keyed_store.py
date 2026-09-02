"""Unit tests for :class:`spectre.core.keyed_store.KeyedJsonStore` in isolation - the generic
persistence StepPresetStore and StructureLibraryStore are now both thin wrappers around, but which
until now was only ever exercised indirectly through the full HTTP routes in
test_step_presets.py/test_structure_library.py.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from spectre.core.keyed_store import KeyedJsonStore


class _Item(BaseModel):
    name: str
    value: int = 0


class _Library(BaseModel):
    items: dict[str, _Item] = Field(default_factory=dict)


def _store(tmp_path: Path, filename: str = "lib.json") -> KeyedJsonStore[_Library, _Item]:
    return KeyedJsonStore(tmp_path / filename, _Library, "items")


def test_load_with_no_file_yet_returns_an_empty_library(tmp_path):
    store = _store(tmp_path)
    assert store.load().items == {}
    assert store.load_items() == {}


def test_upsert_writes_the_file_and_is_readable_back(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    assert (tmp_path / "lib.json").exists()
    assert store.load_items()["A"].value == 1


def test_upsert_overwrites_an_existing_entry_with_the_same_name(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    store.upsert(_Item(name="A", value=2))
    assert len(store.load_items()) == 1
    assert store.load_items()["A"].value == 2


def test_rename_moves_the_entry_to_the_new_key(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    store.rename("A", _Item(name="B", value=1))
    items = store.load_items()
    assert "A" not in items
    assert items["B"].value == 1


def test_rename_to_the_same_name_just_replaces_it(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    store.rename("A", _Item(name="A", value=9))
    assert store.load_items()["A"].value == 9


def test_remove_deletes_the_entry(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    store.remove("A")
    assert store.load_items() == {}


def test_remove_of_a_missing_name_is_a_no_op(tmp_path):
    store = _store(tmp_path)
    store.upsert(_Item(name="A", value=1))
    store.remove("does-not-exist")
    assert list(store.load_items()) == ["A"]


def test_two_stores_over_the_same_path_see_each_others_writes(tmp_path):
    path = tmp_path / "lib.json"
    store_a = KeyedJsonStore(path, _Library, "items")
    store_b = KeyedJsonStore(path, _Library, "items")
    store_a.upsert(_Item(name="A", value=1))
    assert store_b.load_items()["A"].value == 1
