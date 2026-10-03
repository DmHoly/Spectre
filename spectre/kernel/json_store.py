"""Persistance des bibliothèques en fichiers JSON : un fichier par collection, lu et écrit sous un
verrou par chemin (:func:`spectre.kernel.locks.keyed_lock`), écrit de façon atomique (fichier
temporaire du même dossier, puis :func:`spectre.kernel.fs.replace`) - un lecteur voit l'ancien contenu ou le nouveau,
jamais un fichier à moitié écrit.

Chaque élément est validé seul : un élément illisible est signalé dans le journal et laissé de côté
à la lecture, sans faire échouer la liste entière ; il est conservé tel quel à l'écriture suivante,
pour qu'une correction à la main reste possible.

- :class:`ItemStore` : une liste d'éléments ``{"items": [...]}``, chacun porteur de son ``id`` - les
  bibliothèques de ``process_library``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from . import fs
from .errors import Unavailable
from .locks import keyed_lock

logger = logging.getLogger(__name__)

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
    """Remplace ``path`` par ``data`` : fichier temporaire du même dossier, puis :func:`~spectre.kernel.fs.replace`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        fs.replace(tmp, path)
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
