"""Persistance des bibliothèques en fichiers JSON : un fichier par collection, lu et écrit sous un
verrou par chemin (:func:`spectre.kernel.locks.keyed_lock`), écrit de façon atomique (fichier
temporaire du même dossier, puis ``os.replace``) - un lecteur voit l'ancien contenu ou le nouveau,
jamais un fichier à moitié écrit.

Chaque élément est validé seul : un élément illisible est signalé dans le journal et laissé de côté
à la lecture, sans faire échouer la liste entière ; il est conservé tel quel à l'écriture suivante,
pour qu'une correction à la main reste possible.

- :class:`ItemStore` : une liste d'éléments ``{"items": [...]}``, chacun porteur de son ``id`` - les
  bibliothèques de ``process_library``.
- :class:`KeyedJsonStore` : un dict d'éléments indexés par leur nom (``{"<champ>": {nom: ...}}``) -
  les formulaires d'intention.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generic, TypeVar, get_args

from pydantic import BaseModel, ValidationError

from .errors import Unavailable
from .locks import keyed_lock

logger = logging.getLogger(__name__)

LibraryT = TypeVar("LibraryT", bound=BaseModel)
ItemT = TypeVar("ItemT", bound=BaseModel)

_LOCK_NAMESPACE = "json_store"


def path_lock(path: Path):
    """Le verrou de ``path``, à tenir autour de :func:`read_json` / :func:`write_json` - les stores
    ci-dessous le prennent eux-mêmes."""
    return keyed_lock(_LOCK_NAMESPACE, str(path.resolve()))


def read_json(path: Path, *, strict: bool) -> dict[str, Any]:
    """Le contenu de ``path`` (``{}`` s'il n'existe pas). Un fichier illisible est signalé ; en
    lecture seule (``strict=False``) il vaut ``{}``, avant une écriture il lève
    :class:`~spectre.kernel.errors.Unavailable` - l'écraser perdrait tout son contenu."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"attendu un objet JSON, reçu {type(data).__name__}")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.error("Fichier JSON illisible %s (%s).", path, exc)
        if strict:
            raise Unavailable(f"Le fichier {path.name} est illisible : corrigez-le avant toute modification.") from exc
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Remplace ``path`` par ``data`` : fichier temporaire du même dossier, puis ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _valid(item_cls: type[ItemT], raw: Any, path: Path, where: str) -> ItemT | None:
    try:
        return item_cls.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Élément invalide ignoré dans %s (%s) : %s", path, where, exc)
        return None


class ItemStore(Generic[ItemT]):
    """Une collection ``{"items": [<élément>, ...]}`` persistée dans ``path``."""

    def __init__(self, path: str | Path, item_cls: type[ItemT]):
        self.path = Path(path)
        self._item_cls = item_cls

    def load(self) -> list[ItemT]:
        """Les éléments valides, dans l'ordre du fichier."""
        with path_lock(self.path):
            raw_items = read_json(self.path, strict=False).get("items") or []
        items = (_valid(self._item_cls, raw, self.path, f"élément {i}") for i, raw in enumerate(raw_items))
        return [item for item in items if item is not None]

    @contextmanager
    def edit(self) -> Iterator[list[dict[str, Any]]]:
        """Les éléments bruts (dicts JSON), à modifier sur place ; réécrits à la sortie du bloc, sous
        le verrou du fichier. Une exception dans le bloc n'écrit rien."""
        with path_lock(self.path):
            data = read_json(self.path, strict=True)
            items = list(data.get("items") or [])
            yield items
            write_json(self.path, {**data, "items": items})


class KeyedJsonStore(Generic[LibraryT, ItemT]):
    """Persists a ``library_cls`` instance (a :class:`~pydantic.BaseModel` with a single
    ``dict[str, ItemT]`` field named ``items_field``) as JSON at ``path``. Items are keyed by
    their own ``.name`` on :meth:`upsert`/:meth:`rename`.
    """

    def __init__(self, path: str | Path, library_cls: type[LibraryT], items_field: str):
        self.path = Path(path)
        self._library_cls = library_cls
        self._items_field = items_field
        self._item_cls = get_args(library_cls.model_fields[items_field].annotation)[1]  # dict[str, ItemT]

    def load(self) -> LibraryT:
        return self._library_cls.model_validate({self._items_field: self.load_items()})

    def save(self, library: LibraryT) -> None:
        with path_lock(self.path):
            write_json(self.path, library.model_dump(mode="json"))

    def load_items(self) -> dict[str, ItemT]:
        """The valid items, by name - an invalid one is logged and left out."""
        with path_lock(self.path):
            raw_items = read_json(self.path, strict=False).get(self._items_field) or {}
        items = {name: _valid(self._item_cls, raw, self.path, repr(name)) for name, raw in raw_items.items()}
        return {name: item for name, item in items.items() if item is not None}

    @contextmanager
    def _edit(self) -> Iterator[dict[str, Any]]:
        with path_lock(self.path):
            data = read_json(self.path, strict=True)
            items = dict(data.get(self._items_field) or {})
            yield items
            write_json(self.path, {**data, self._items_field: items})

    def upsert(self, item: ItemT) -> LibraryT:
        with self._edit() as items:
            items[item.name] = item.model_dump(mode="json")
        return self.load()

    def rename(self, old_name: str, item: ItemT) -> LibraryT:
        """Replace whatever is saved under ``old_name`` with ``item`` - used when editing an
        entry in place also changes its name, so the old key doesn't linger.
        """
        with self._edit() as items:
            items.pop(old_name, None)
            items[item.name] = item.model_dump(mode="json")
        return self.load()

    def remove(self, name: str) -> LibraryT:
        with self._edit() as items:
            items.pop(name, None)
        return self.load()
