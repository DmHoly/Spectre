"""Unit tests for :mod:`spectre.kernel.json_store` in isolation: :class:`ItemStore` (the process
libraries) - atomic, locked writes and item-by-item validation.
"""

from __future__ import annotations

import json
import threading

import pytest
from pydantic import BaseModel

from spectre.kernel import json_store
from spectre.kernel.errors import Unavailable
from spectre.kernel.json_store import ItemStore


class _Element(BaseModel):
    id: str
    name: str


def test_two_stores_over_the_same_path_see_each_others_writes(tmp_path):
    path = tmp_path / "items.json"
    store_a = ItemStore(path, _Element)
    store_b = ItemStore(path, _Element)
    with store_a.edit() as items:
        items.append({"id": "1", "name": "A"})
    assert store_b.load() == [_Element(id="1", name="A")]


def test_an_invalid_item_is_left_out_of_the_reading_and_kept_on_the_next_write(tmp_path):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"items": [{"id": "1", "name": "A"}, {"id": "2", "name": ["pas un nom"]}]}), encoding="utf-8")
    store = ItemStore(path, _Element)

    assert [item.id for item in store.load()] == ["1"]
    with store.edit() as items:
        items.append({"id": "3", "name": "C"})
    assert json.loads(path.read_text(encoding="utf-8"))["items"][1] == {"id": "2", "name": ["pas un nom"]}


def test_an_unreadable_file_reads_as_empty_but_is_never_overwritten(tmp_path):
    path = tmp_path / "items.json"
    path.write_text("{ pas du json", encoding="utf-8")
    store = ItemStore(path, _Element)

    assert store.load() == []
    with pytest.raises(Unavailable):
        with store.edit() as items:
            items.append({"id": "1", "name": "A"})
    assert path.read_text(encoding="utf-8") == "{ pas du json"


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
