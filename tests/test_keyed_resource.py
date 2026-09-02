"""Unit tests for spectre.api.keyed_resource - the shared body of the list/create/update route
handlers, exercised here directly (no HTTP client) rather than only indirectly through the full
request/response round-trips in test_step_presets.py/test_structure_library.py.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field

from spectre.api.keyed_resource import list_three_buckets, reject_duplicate, require_existing
from spectre.core.keyed_store import KeyedJsonStore


class _Item(BaseModel):
    name: str


class _Library(BaseModel):
    items: dict[str, _Item] = Field(default_factory=dict)


def _store(tmp_path, filename: str) -> KeyedJsonStore[_Library, _Item]:
    return KeyedJsonStore(tmp_path / filename, _Library, "items")


def test_list_three_buckets_orders_presets_then_shared_then_own(tmp_path):
    own = _store(tmp_path, "own.json")
    shared = _store(tmp_path, "shared.json")
    own.upsert(_Item(name="Mine"))
    shared.upsert(_Item(name="Shared"))
    defaults = {"Built-in": _Item(name="Built-in")}

    result = list_three_buckets(own, shared, defaults, lambda item, scope: {"name": item.name, "scope": scope})

    assert result == {
        "presets": [{"name": "Built-in", "scope": "preset"}],
        "partagees": [{"name": "Shared", "scope": "partagee"}],
        "projet": [{"name": "Mine", "scope": "projet"}],
    }


def test_reject_duplicate_raises_409_when_the_name_is_already_taken(tmp_path):
    store = _store(tmp_path, "lib.json")
    store.upsert(_Item(name="A"))
    with pytest.raises(HTTPException) as exc_info:
        reject_duplicate(store, "A", message="deja pris")
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "deja pris"


def test_reject_duplicate_is_silent_when_the_name_is_free(tmp_path):
    store = _store(tmp_path, "lib.json")
    reject_duplicate(store, "A", message="deja pris")  # must not raise


def test_require_existing_returns_the_item_when_present(tmp_path):
    store = _store(tmp_path, "lib.json")
    store.upsert(_Item(name="A"))
    assert require_existing(store, "A", message="introuvable").name == "A"


def test_require_existing_raises_404_when_missing(tmp_path):
    store = _store(tmp_path, "lib.json")
    with pytest.raises(HTTPException) as exc_info:
        require_existing(store, "missing", message="introuvable")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "introuvable"
