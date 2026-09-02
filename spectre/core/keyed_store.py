"""A JSON-backed store for a named, keyed collection - the shape shared by the structure library
(:mod:`spectre.core.structure_library`) and the step preset library (:mod:`spectre.core.
step_presets`): a dict of named items, persisted as one JSON file, with identical load/save/
upsert/rename/remove behaviour across both. The only thing that differs between the two is the
Pydantic model wrapping the dict (``StructureLibrary.structures`` vs. ``StepPresetLibrary.
presets``) and the item type inside it - both supplied here rather than duplicated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

LibraryT = TypeVar("LibraryT", bound=BaseModel)
ItemT = TypeVar("ItemT", bound=BaseModel)


class KeyedJsonStore(Generic[LibraryT, ItemT]):
    """Persists a ``library_cls`` instance (a :class:`~pydantic.BaseModel` with a single
    ``dict[str, ItemT]`` field named ``items_field``) as JSON at ``path``. Items are keyed by
    their own ``.name`` on :meth:`upsert`/:meth:`rename`.
    """

    def __init__(self, path: str | Path, library_cls: type[LibraryT], items_field: str):
        self.path = Path(path)
        self._library_cls = library_cls
        self._items_field = items_field

    def load(self) -> LibraryT:
        if not self.path.exists():
            return self._library_cls()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return self._library_cls.model_validate(data)

    def save(self, library: LibraryT) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(library.model_dump_json(indent=2), encoding="utf-8")

    def load_items(self) -> dict[str, ItemT]:
        """The items dict directly, regardless of what it's called on the underlying model -
        what every caller actually wants (list/lookup/duplicate-check), without needing to know
        whether the field is named ``structures`` or ``presets``.
        """
        return self._items_of(self.load())

    def _items_of(self, library: LibraryT) -> dict[str, ItemT]:
        return getattr(library, self._items_field)

    def upsert(self, item: ItemT) -> LibraryT:
        library = self.load()
        self._items_of(library)[item.name] = item
        self.save(library)
        return library

    def rename(self, old_name: str, item: ItemT) -> LibraryT:
        """Replace whatever is saved under ``old_name`` with ``item`` - used when editing an
        entry in place also changes its name, so the old key doesn't linger.
        """
        library = self.load()
        items = self._items_of(library)
        items.pop(old_name, None)
        items[item.name] = item
        self.save(library)
        return library

    def remove(self, name: str) -> LibraryT:
        library = self.load()
        self._items_of(library).pop(name, None)
        self.save(library)
        return library
