"""Unit tests for :mod:`spectre.kernel.json_store` in isolation: :class:`KeyedJsonStore` (the
intent forms) and :class:`ItemStore` (the process libraries) - atomic, locked writes and
item-by-item validation.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from spectre.kernel import json_store
from spectre.kernel.errors import Unavailable
from spectre.kernel.json_store import ItemStore, KeyedJsonStore


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


def test_an_invalid_item_is_left_out_of_the_reading_and_kept_on_the_next_write(tmp_path):
    path = tmp_path / "lib.json"
    path.write_text(json.dumps({"items": {"A": {"name": "A", "value": 1}, "B": {"name": "B", "value": "pas un entier"}}}), encoding="utf-8")
    store = KeyedJsonStore(path, _Library, "items")

    assert list(store.load_items()) == ["A"]
    store.upsert(_Item(name="C", value=3))
    assert json.loads(path.read_text(encoding="utf-8"))["items"]["B"] == {"name": "B", "value": "pas un entier"}


def test_an_unreadable_file_reads_as_empty_but_is_never_overwritten(tmp_path):
    path = tmp_path / "lib.json"
    path.write_text("{ pas du json", encoding="utf-8")
    store = KeyedJsonStore(path, _Library, "items")

    assert store.load_items() == {}
    with pytest.raises(Unavailable):
        store.upsert(_Item(name="A"))
    assert path.read_text(encoding="utf-8") == "{ pas du json"


class _Element(BaseModel):
    id: str
    name: str


def test_item_store_round_trip_and_invalid_items(tmp_path):
    path = tmp_path / "items.json"
    store = ItemStore(path, _Element)
    assert store.load() == []

    with store.edit() as items:
        items.append({"id": "1", "name": "Un"})
        items.append({"id": "2"})  # sans nom : invalide
    assert store.load() == [_Element(id="1", name="Un")]

    with store.edit() as items:
        items.append({"id": "3", "name": "Trois"})
    assert [raw["id"] for raw in json.loads(path.read_text(encoding="utf-8"))["items"]] == ["1", "2", "3"]


def test_an_error_inside_an_edit_writes_nothing(tmp_path):
    store = ItemStore(tmp_path / "items.json", _Element)
    with store.edit() as items:
        items.append({"id": "1", "name": "Un"})

    with pytest.raises(RuntimeError), store.edit() as items:
        items.clear()
        raise RuntimeError("abandon")
    assert [item.id for item in store.load()] == ["1"]


def test_a_failed_write_keeps_the_old_file_and_no_temporary_file(tmp_path, monkeypatch):
    store = ItemStore(tmp_path / "items.json", _Element)
    with store.edit() as items:
        items.append({"id": "1", "name": "Un"})

    def broken_replace(src, dst):
        raise OSError("disque plein")

    monkeypatch.setattr(json_store.os, "replace", broken_replace)
    with pytest.raises(OSError), store.edit() as items:
        items.append({"id": "2", "name": "Deux"})
    assert [item.id for item in store.load()] == ["1"]
    assert [path.name for path in tmp_path.iterdir()] == ["items.json"]


def test_concurrent_edits_do_not_lose_writes(tmp_path):
    store = ItemStore(tmp_path / "items.json", _Element)

    def add(i: int) -> None:
        with store.edit() as items:
            items.append({"id": str(i), "name": f"n{i}"})

    threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(int(item.id) for item in store.load()) == list(range(20))
