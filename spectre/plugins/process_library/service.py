"""Les trois bibliothèques (structures enregistrées, présets d'étape, briques) sont des collections
à plat d'éléments identifiés par un ``id`` opaque, chacun dans l'une de trois portées :

- ``builtin`` : les éléments livrés avec l'instance (fichiers YAML de ``library``), en lecture
  seule ici. Leur ``id`` dérive de leur nom ;
- ``shared`` : visibles depuis tous les µprojets (``<données>/<collection>_partage(e)s.json``).
  Tout compte connecté en crée ; seuls leur auteur et un administrateur les modifient ou les
  suppriment. Un élément partagé antérieur à cette traçabilité n'a pas d'auteur connu
  (``created_by`` vaut ``None``) : seul un administrateur peut alors le modifier ou le supprimer ;
- ``microproject`` : propres à un µprojet (``<données>/microprojects/<slug>/<collection>.json``,
  supprimés avec lui), lus par ses membres et écrits par ses ``editor``.

Le nom n'est qu'un champ : il est unique dans sa portée (et son µprojet), un renommage vers un nom
pris est refusé (409). La portée se change par une modification, comme le nom. Les écritures d'une
collection sont sérialisées par un verrou (``kernel.locks``) : la vérification du nom et le
déplacement d'un fichier à l'autre se font d'un bloc.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, Literal, TypeVar

from pydantic import ValidationError

from ...kernel.db import data_dir
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ...kernel.json_store import ItemStore
from ...kernel.locks import keyed_lock
from ..accounts.service import User
from ..microprojects import service as microprojects
from ..microprojects.service import ROLE_ORDER, Microproject
from ..structures import simulation
from .models import LibraryItem
from .step_presets import StepPreset, default_step_presets
from .structure_library import SavedStructure, default_structure_presets
from .tech_bricks import TechBrick, default_tech_bricks

ItemT = TypeVar("ItemT", bound=LibraryItem)
Scope = Literal["builtin", "shared", "microproject"]
SCOPES: tuple[Scope, ...] = ("builtin", "shared", "microproject")


@dataclass(frozen=True)
class Collection(Generic[ItemT]):
    key: str  # celui de l'API : "saved-structures"
    item_cls: type[ItemT]
    filename: str  # dans le dossier d'un µprojet
    shared_filename: str  # dans le dossier des données
    builtins: Callable[[], dict[str, ItemT]]  # par nom
    duplicate: str  # message d'un nom déjà pris, avec {name}
    missing: str  # message d'un élément introuvable
    check: Callable[[ItemT], None] | None = None  # règle propre à la collection ; InvalidInput

    def shared_store(self) -> ItemStore[ItemT]:
        return ItemStore(data_dir() / self.shared_filename, self.item_cls)

    def microproject_store(self, slug: str) -> ItemStore[ItemT]:
        return ItemStore(microprojects.microproject_dir(slug) / self.filename, self.item_cls)

    def store(self, microproject: Microproject | None) -> ItemStore[ItemT]:
        return self.microproject_store(microproject.slug) if microproject else self.shared_store()


@dataclass(frozen=True)
class Entry(Generic[ItemT]):
    """Un élément et l'endroit où il est rangé."""

    item: ItemT
    scope: Scope
    microproject: Microproject | None = None


def builtin_id(name: str) -> str:
    return "builtin-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock(collection: Collection):
    return keyed_lock("process_library", collection.key)


# -- droits ----------------------------------------------------------------------------------------


def _role(microproject: Microproject, user: User) -> int:
    role = microprojects.effective_role(user, microproject)
    return -1 if role is None else ROLE_ORDER[role]


def can_read(entry: Entry, user: User) -> bool:
    return entry.microproject is None or _role(entry.microproject, user) >= ROLE_ORDER["viewer"]


def can_edit(entry: Entry, user: User) -> bool:
    if entry.scope == "builtin":
        return False
    if entry.scope == "shared":
        return user.is_admin or (entry.item.created_by is not None and entry.item.created_by == user.id)
    return _role(entry.microproject, user) >= ROLE_ORDER["editor"]


def _require_edit(entry: Entry, user: User) -> None:
    if entry.scope == "builtin":
        raise Forbidden("Un élément intégré se modifie dans les fichiers de la bibliothèque (réservé aux administrateurs).")
    if not can_edit(entry, user):
        if entry.scope == "shared":
            raise Forbidden("Seul son auteur ou un administrateur peut modifier ou supprimer un élément partagé.")
        raise Forbidden("Il faut être éditeur de ce µprojet pour modifier ou supprimer cet élément.")


def _microproject(slug: str) -> Microproject:
    try:
        return microprojects.get_by_slug(slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise NotFound(f"µprojet {slug!r} introuvable") from exc


def _target(scope: str, microproject_slug: str | None, user: User) -> Microproject | None:
    """Le µprojet où ranger un élément de portée ``scope`` (``None`` : partagé), après contrôle du
    droit d'y écrire."""
    if scope == "shared":
        return None
    if scope != "microproject":
        raise InvalidInput("Portée invalide : « shared » ou « microproject ».")
    if not microproject_slug:
        raise InvalidInput("Précisez le µprojet d'un élément de portée « microproject ».")
    microproject = _microproject(microproject_slug)
    if _role(microproject, user) < ROLE_ORDER["editor"]:
        raise Forbidden("Il faut être éditeur de ce µprojet pour y ranger un élément.")
    return microproject


# -- lecture ---------------------------------------------------------------------------------------


def _builtin_entries(collection: Collection[ItemT]) -> list[Entry[ItemT]]:
    return [
        Entry(item.model_copy(update={"id": builtin_id(name)}), "builtin")
        for name, item in collection.builtins().items()
    ]


def _entries(collection: Collection[ItemT], microproject: Microproject | None) -> list[Entry[ItemT]]:
    scope: Scope = "microproject" if microproject else "shared"
    return [Entry(item, scope, microproject) for item in collection.store(microproject).load()]


def list_items(
    collection: Collection[ItemT], user: User, *, microproject_slug: str | None = None, scope: str | None = None
) -> list[Entry[ItemT]]:
    """Les éléments intégrés, les partagés, et ceux du µprojet ``microproject_slug`` (lu par un
    membre) ; ``scope`` n'en garde qu'une portée."""
    if scope is not None and scope not in SCOPES:
        raise InvalidInput("Portée invalide : « builtin », « shared » ou « microproject ».")
    microproject = None
    if microproject_slug:
        microproject = _microproject(microproject_slug)
        if _role(microproject, user) < ROLE_ORDER["viewer"]:
            raise Forbidden("Vous n'êtes pas membre de ce µprojet.")
    elif scope == "microproject":
        raise InvalidInput("Précisez le µprojet (?microproject=) pour lister ses éléments.")
    entries = [*_builtin_entries(collection), *_entries(collection, None)]
    if microproject:
        entries += _entries(collection, microproject)
    return [entry for entry in entries if scope is None or entry.scope == scope]


def _find(collection: Collection[ItemT], item_id: str) -> Entry[ItemT] | None:
    if item_id.startswith("builtin-"):
        return next((entry for entry in _builtin_entries(collection) if entry.item.id == item_id), None)
    for microproject in [None, *microprojects.list_all()]:
        for entry in _entries(collection, microproject):
            if entry.item.id == item_id:
                return entry
    return None


def get_item(collection: Collection[ItemT], user: User, item_id: str) -> Entry[ItemT]:
    """L'élément ``item_id`` ; introuvable aussi pour qui ne peut pas le lire."""
    entry = _find(collection, item_id)
    if entry is None or not can_read(entry, user):
        raise NotFound(collection.missing)
    return entry


# -- écriture --------------------------------------------------------------------------------------


def _clean_name(name: Any) -> str:
    name = name.strip() if isinstance(name, str) else ""
    if not name:
        raise InvalidInput("Le nom ne peut pas être vide.")
    return name


def _reject_duplicate(collection: Collection, microproject: Microproject | None, name: str, *, except_id: str | None = None) -> None:
    if any(item.name == name and item.id != except_id for item in collection.store(microproject).load()):
        raise Conflict(collection.duplicate.format(name=name))


def _validated(collection: Collection[ItemT], fields: dict[str, Any]) -> ItemT:
    try:
        item = collection.item_cls.model_validate(fields)
    except ValidationError as exc:
        raise InvalidInput(str(exc)) from exc
    if collection.check:
        collection.check(item)
    return item


def create_item(
    collection: Collection[ItemT], user: User, content: dict[str, Any], *, scope: str, microproject_slug: str | None
) -> Entry[ItemT]:
    """Un nouvel élément ``content`` (son nom et ses champs propres), rangé dans ``scope``."""
    microproject = _target(scope, microproject_slug, user)
    name = _clean_name(content.get("name"))
    item = _validated(
        collection,
        {
            **content,
            "name": name,
            "id": secrets.token_hex(8),
            "created_by": user.id,
            "updated_by": user.id,
            "created_at": _now(),
        },
    )
    with _lock(collection):
        _reject_duplicate(collection, microproject, name)
        with collection.store(microproject).edit() as items:
            items.append(item.model_dump(mode="json"))
    return Entry(item, "microproject" if microproject else "shared", microproject)


def update_item(collection: Collection[ItemT], user: User, item_id: str, changes: dict[str, Any]) -> Entry[ItemT]:
    """Applique ``changes`` (champs de l'élément, et ``scope`` / ``microproject`` pour le déplacer)
    à l'élément ``item_id``. Sans effet, rien n'est écrit."""
    changes = dict(changes)
    with _lock(collection):
        entry = get_item(collection, user, item_id)
        _require_edit(entry, user)
        source = entry.microproject
        source_slug = source.slug if source else None
        scope = changes.pop("scope", None) or entry.scope
        requested_slug = changes.pop("microproject", None)
        slug = (requested_slug or source_slug) if scope == "microproject" else None
        target = source if (scope, slug) == (entry.scope, source_slug) else _target(scope, slug, user)
        moved = target is not source
        if "name" in changes:
            changes["name"] = _clean_name(changes["name"])
        current = entry.item.model_dump(mode="json")
        item = _validated(collection, {**current, **changes})
        if not moved and item.model_dump(mode="json") == current:
            return entry
        item = item.model_copy(update={"updated_by": user.id})
        _reject_duplicate(collection, target, item.name, except_id=item.id)
        if moved:
            with collection.store(source).edit() as items:
                items[:] = [raw for raw in items if raw.get("id") != item.id]
            with collection.store(target).edit() as items:
                items.append(item.model_dump(mode="json"))
        else:
            with collection.store(target).edit() as items:
                items[:] = [item.model_dump(mode="json") if raw.get("id") == item.id else raw for raw in items]
    return Entry(item, "microproject" if target else "shared", target)


def delete_item(collection: Collection, user: User, item_id: str) -> None:
    with _lock(collection):
        entry = get_item(collection, user, item_id)
        _require_edit(entry, user)
        with collection.store(entry.microproject).edit() as items:
            items[:] = [raw for raw in items if raw.get("id") != item_id]


# -- les trois collections -------------------------------------------------------------------------


def _check_recipe(preset: StepPreset) -> None:
    """Un préset nomme une recette existante du bon type (dépôt ou gravure)."""
    recipes = simulation.recipes_library()
    known = recipes.deposition if preset.payload.kind == "deposition" else recipes.etch
    if preset.payload.recipe not in known:
        kind = "dépôt" if preset.payload.kind == "deposition" else "gravure"
        raise InvalidInput(f"Recette de {kind} inconnue : {preset.payload.recipe!r}.", code="unknown_recipe")


SAVED_STRUCTURES = Collection(
    key="saved-structures",
    item_cls=SavedStructure,
    filename="structures.json",
    shared_filename="structures_partagees.json",
    builtins=default_structure_presets,
    duplicate="Une structure nommée {name!r} existe déjà dans cette bibliothèque.",
    missing="Structure introuvable.",
)
STEP_PRESETS = Collection(
    key="step-presets",
    item_cls=StepPreset,
    filename="presets_etapes.json",
    shared_filename="presets_etapes_partages.json",
    builtins=default_step_presets,
    duplicate="Un préset nommé {name!r} existe déjà dans cette bibliothèque.",
    missing="Préset introuvable.",
    check=_check_recipe,
)
TECH_BRICKS = Collection(
    key="tech-bricks",
    item_cls=TechBrick,
    filename="briques.json",
    shared_filename="briques_partagees.json",
    builtins=default_tech_bricks,
    duplicate="Une brique nommée {name!r} existe déjà dans cette bibliothèque.",
    missing="Brique introuvable.",
)
COLLECTIONS: tuple[Collection, ...] = (SAVED_STRUCTURES, STEP_PRESETS, TECH_BRICKS)


def legacy_files() -> list[tuple[Path, str]]:
    """Chaque fichier de bibliothèque existant, avec la clé de son ancien format
    (``{"structures": {nom: …}}``) - pour la migration qui leur donne un ``id``."""
    legacy_keys = {"saved-structures": "structures", "step-presets": "presets", "tech-bricks": "bricks"}
    root = data_dir()
    found = []
    for collection in COLLECTIONS:
        paths = [root / collection.shared_filename, *sorted((root / "microprojects").glob(f"*/{collection.filename}"))]
        found += [(path, legacy_keys[collection.key]) for path in paths if path.is_file()]
    return found
