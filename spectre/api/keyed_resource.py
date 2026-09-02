"""The shared body of the four route handlers (list/create/update/delete) that both the step
preset routes and the saved structure routes (:mod:`spectre.api.structures`) implement over a
:class:`~spectre.core.keyed_store.KeyedJsonStore`: a three-bucket listing (built-in / shared /
project's own), a duplicate-name guard on create, and a not-found guard on update. Route
declarations themselves stay explicit per resource (distinct request/response models, distinct
permissions) - only this common body is factored out.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from fastapi import HTTPException

from ..core.keyed_store import KeyedJsonStore

ItemT = TypeVar("ItemT")


def list_three_buckets(
    own_store: KeyedJsonStore, shared_store: KeyedJsonStore, defaults: dict[str, ItemT], payload_of: Callable[[ItemT, str], dict]
) -> dict:
    """Built-in presets (scope ``"preset"``), then the shared store (``"partagee"``), then the
    project's own (``"projet"``) - the response shape both resources return from their ``GET``
    and, to reflect the change made, from every mutating route too.
    """
    return {
        "presets": [payload_of(item, "preset") for item in defaults.values()],
        "partagees": [payload_of(item, "partagee") for item in shared_store.load_items().values()],
        "projet": [payload_of(item, "projet") for item in own_store.load_items().values()],
    }


def reject_duplicate(store: KeyedJsonStore, name: str, *, message: str) -> None:
    if name in store.load_items():
        raise HTTPException(status_code=409, detail=message)


def require_existing(store: KeyedJsonStore, name: str, *, message: str) -> ItemT:
    existing = store.load_items().get(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=message)
    return existing
