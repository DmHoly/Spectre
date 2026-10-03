"""Formulaires d'intention : une bibliothèque de questionnaires qu'un µprojet choisit comme
formulaire actif - les questions posées systématiquement à chaque nouvelle expérience/évolution
(qui a lancé ce run, sur quel équipement, un risque identifié...) plutôt que confiées à un champ de
texte libre que personne n'est obligé de bien remplir.

Follow n'a rien de nouveau à apprendre ici : :class:`follow.storage.commit_form.CommitForm` (un
YAML de questions structurées - label, type, choix, obligatoire ou non) existe déjà, et un dépôt
Follow lit ``<dépôt>/commit_form.yml`` à chaque ouverture. Ce que Spectre ajoute :

- la **bibliothèque**, deux étagères : partagée entre µprojets (``data_dir/intent_forms.json``) et
  propre à un µprojet (``microprojects/<slug>/intent_forms.json``). Chaque entrée a un ``id`` opaque ;
  le nom n'est qu'un champ, unique dans son étagère ;
- le **formulaire actif** d'un µprojet : une *copie* de l'entrée choisie, écrite en
  ``commit_form.yml``. Ce fichier est la seule vérité - son origine (``form_id``, ``name``) est
  notée dans un commentaire d'en-tête, que Follow ignore. Modifier ou supprimer l'entrée de
  bibliothèque ne change pas le formulaire appliqué (sémantique d'instantané) : la lecture signale
  seulement ``outdated`` tant qu'on ne l'a pas réactivée.

Droits : une entrée partagée se crée par tout compte connecté et se modifie par son auteur ou un
admin ; une entrée de µprojet, comme le formulaire actif, demande le rôle ``editor`` sur ce µprojet.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from follow.storage.commit_form import CommitForm
from pydantic import BaseModel, Field, ValidationError

from ...kernel.db import data_dir
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ...kernel.locks import keyed_lock
from ..accounts.service import User
from ..experiments.repository import follow_repo_path
from ..microprojects import service as microprojects
from ..microprojects.service import ROLE_ORDER, MicroprojectNotFoundError

SCOPES = ("builtin", "shared", "microproject")
LIBRARY_FILE = "intent_forms.json"
ACTIVE_FILE = "commit_form.yml"
ORIGIN_MARK = "# spectre-intent-form: "


class IntentForm(BaseModel):
    id: str
    name: str
    form: CommitForm
    created_at: str
    updated_at: str | None = None
    created_by_id: int | None = None
    created_by: str | None = None
    updated_by: str | None = None


class IntentFormFile(BaseModel):
    forms: dict[str, IntentForm] = Field(default_factory=dict)


@dataclass(frozen=True)
class LibraryEntry:
    """Une entrée et son étagère : ``microproject`` vaut ``None`` pour la bibliothèque partagée."""

    item: IntentForm
    microproject: str | None

    @property
    def scope(self) -> str:
        return "shared" if self.microproject is None else "microproject"


@dataclass(frozen=True)
class ActiveForm:
    form: CommitForm
    origin: dict | None  # {"form_id", "name"} de l'entrée activée, None pour un fichier posé à la main
    outdated: bool


# --- formulaires YAML -------------------------------------------------------------------------


def parse_yaml_form(text: str) -> CommitForm:
    """Le texte d'un formulaire (un fichier choisi dans le navigateur), validé comme
    :func:`follow.storage.commit_form.load_commit_form` le ferait depuis un chemin."""
    try:
        payload = yaml.safe_load(text) or {}
        if not isinstance(payload, dict):
            raise ValueError("le fichier doit être un document YAML avec des champs 'title'/'fields'")
        return CommitForm.model_validate(payload)
    except (yaml.YAMLError, ValueError, ValidationError) as exc:
        raise InvalidInput(f"Fichier de formulaire invalide : {exc}") from exc


def dump_yaml_form(form: CommitForm) -> str:
    return yaml.safe_dump(form.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False)


def _write_atomically(path: Path, text: str) -> None:
    # Follow relit commit_form.yml à chaque ouverture du dépôt : jamais un fichier à moitié écrit
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# --- étagères ---------------------------------------------------------------------------------


def _shelf_path(microproject: str | None) -> Path:
    if microproject is None:
        return data_dir() / LIBRARY_FILE
    return microprojects.microproject_dir(microproject) / LIBRARY_FILE


def _load(path: Path) -> dict[str, IntentForm]:
    if not path.exists():
        return {}
    return IntentFormFile.model_validate_json(path.read_text(encoding="utf-8")).forms


def _save(path: Path, forms: dict[str, IntentForm]) -> None:
    _write_atomically(path, IntentFormFile(forms=forms).model_dump_json(indent=2))


def _shelf_lock(microproject: str | None):
    return keyed_lock("intent_forms", microproject or "")


def _find(form_id: str) -> LibraryEntry:
    """L'entrée ``form_id``, dans la bibliothèque partagée ou dans celle d'un µprojet."""
    shared = _load(_shelf_path(None))
    if form_id in shared:
        return LibraryEntry(shared[form_id], None)
    root = data_dir() / "microprojects"
    for path in sorted(root.glob(f"*/{LIBRARY_FILE}")) if root.exists() else ():
        forms = _load(path)
        if form_id in forms:
            return LibraryEntry(forms[form_id], path.parent.name)
    raise NotFound(f"Formulaire d'intention {form_id!r} introuvable.")


def _check_name_free(forms: dict[str, IntentForm], name: str, *, except_id: str | None = None) -> None:
    if any(item.name == name and item.id != except_id for item in forms.values()):
        raise Conflict(f"Un formulaire nommé {name!r} existe déjà dans cette bibliothèque.", code="duplicate_name")


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise InvalidInput("Le nom du formulaire est obligatoire.")
    return name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- droits -----------------------------------------------------------------------------------


def _role(user: User, slug: str) -> str | None:
    try:
        microproject = microprojects.get_by_slug(slug)
    except MicroprojectNotFoundError as exc:
        raise NotFound(f"projet {slug!r} introuvable") from exc
    return microprojects.role_for(microproject.id, user.id)


def require_role(user: User, slug: str, min_role: str) -> None:
    role = _role(user, slug)
    if role is None or ROLE_ORDER[role] < ROLE_ORDER[min_role]:
        raise Forbidden("vous n'avez pas les droits nécessaires pour cette action")


def can_edit(user: User, entry: LibraryEntry) -> bool:
    if entry.microproject is None:
        return user.is_admin or (entry.item.created_by_id is not None and entry.item.created_by_id == user.id)
    role = _role(user, entry.microproject)
    return role is not None and ROLE_ORDER[role] >= ROLE_ORDER["editor"]


def _require_edit(user: User, entry: LibraryEntry) -> None:
    if not can_edit(user, entry):
        if entry.microproject is None:
            raise Forbidden("Seul l'auteur de ce formulaire partagé, ou un administrateur, peut le modifier.")
        raise Forbidden("vous n'avez pas les droits nécessaires pour cette action")


# --- bibliothèque -----------------------------------------------------------------------------


def list_forms(user: User, *, microproject: str | None = None, scope: str | None = None) -> list[LibraryEntry]:
    """Les entrées visibles : la bibliothèque partagée, plus celle de ``microproject`` s'il est
    donné (rôle ``viewer``). ``scope`` filtre sur une portée (aucun formulaire n'est intégré)."""
    if scope is not None and scope not in SCOPES:
        raise InvalidInput(f"Portée inconnue : {scope!r} (builtin, shared ou microproject).")
    if scope == "microproject" and microproject is None:
        raise InvalidInput("La portée microproject demande le paramètre microproject.")
    if microproject is not None:
        require_role(user, microproject, "viewer")
    entries = []
    if scope in (None, "shared"):
        entries += [LibraryEntry(item, None) for item in _load(_shelf_path(None)).values()]
    if microproject is not None and scope in (None, "microproject"):
        entries += [LibraryEntry(item, microproject) for item in _load(_shelf_path(microproject)).values()]
    return entries


def get_form(user: User, form_id: str) -> LibraryEntry:
    entry = _find(form_id)
    if entry.microproject is not None:
        require_role(user, entry.microproject, "viewer")
    return entry


def create_form(user: User, *, name: str, yaml_text: str, scope: str, microproject: str | None = None) -> LibraryEntry:
    if scope == "shared":
        microproject = None
    elif scope == "microproject":
        if not microproject:
            raise InvalidInput("Un formulaire de portée microproject doit nommer son µprojet.")
        require_role(user, microproject, "editor")
    else:
        raise InvalidInput("La portée d'un nouveau formulaire est shared ou microproject.")
    name = _clean_name(name)
    form = parse_yaml_form(yaml_text)
    path = _shelf_path(microproject)
    with _shelf_lock(microproject):
        forms = _load(path)
        _check_name_free(forms, name)
        now = _now()
        item = IntentForm(
            id=secrets.token_hex(8),
            name=name,
            form=form,
            created_at=now,
            updated_at=now,
            created_by_id=user.id,
            created_by=user.name,
            updated_by=user.name,
        )
        forms[item.id] = item
        _save(path, forms)
    return LibraryEntry(item, microproject)


def update_form(user: User, form_id: str, *, name: str | None = None, yaml_text: str | None = None) -> LibraryEntry:
    """Renomme l'entrée ou remplace ses questions. Le formulaire actif d'un µprojet qui l'a
    activée n'en change pas : il faut la réactiver (voir :func:`get_active`, ``outdated``)."""
    entry = _find(form_id)
    _require_edit(user, entry)
    changes: dict = {}
    if name is not None:
        changes["name"] = _clean_name(name)
    if yaml_text is not None:
        changes["form"] = parse_yaml_form(yaml_text)
    path = _shelf_path(entry.microproject)
    with _shelf_lock(entry.microproject):
        forms = _load(path)
        current = forms.get(form_id)
        if current is None:
            raise NotFound(f"Formulaire d'intention {form_id!r} introuvable.")
        if all(getattr(current, key) == value for key, value in changes.items()):
            return LibraryEntry(current, entry.microproject)  # rien ne change
        if "name" in changes:
            _check_name_free(forms, changes["name"], except_id=form_id)
        item = current.model_copy(update={**changes, "updated_at": _now(), "updated_by": user.name})
        forms[form_id] = item
        _save(path, forms)
    return LibraryEntry(item, entry.microproject)


def delete_form(user: User, form_id: str) -> None:
    """Retire l'entrée de sa bibliothèque. Les µprojets qui l'avaient activée gardent leur copie."""
    entry = _find(form_id)
    _require_edit(user, entry)
    path = _shelf_path(entry.microproject)
    with _shelf_lock(entry.microproject):
        forms = _load(path)
        if forms.pop(form_id, None) is not None:
            _save(path, forms)


# --- formulaire actif d'un µprojet --------------------------------------------------------------


def _active_path(slug: str) -> Path:
    return follow_repo_path(slug) / ACTIVE_FILE


def _read_origin(text: str) -> dict | None:
    first_line = text.split("\n", 1)[0]
    if not first_line.startswith(ORIGIN_MARK):
        return None
    try:
        origin = json.loads(first_line[len(ORIGIN_MARK) :])
    except ValueError:
        return None
    return origin if isinstance(origin, dict) and "form_id" in origin else None


def _write_active(slug: str, form: CommitForm, origin: dict | None) -> None:
    header = f"{ORIGIN_MARK}{json.dumps(origin, ensure_ascii=False)}\n" if origin is not None else ""
    _write_atomically(_active_path(slug), header + dump_yaml_form(form))


def _read_active(slug: str) -> ActiveForm | None:
    path = _active_path(slug)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    form = parse_yaml_form(text)
    origin = _read_origin(text)
    outdated = False
    if origin is not None:
        try:
            outdated = _find(origin["form_id"]).item.form != form
        except NotFound:
            pass  # l'entrée a quitté la bibliothèque : il n'y a rien à réactiver
    return ActiveForm(form, origin, outdated)


def get_active(user: User, slug: str) -> ActiveForm:
    require_role(user, slug, "viewer")
    active = _read_active(slug)
    if active is None:
        raise NotFound("Aucun formulaire d'intention actif sur ce µprojet.", code="no_active_intent_form")
    return active


def activate(user: User, slug: str, form_id: str) -> ActiveForm:
    """Copie l'entrée ``form_id`` (partagée, ou de ce µprojet) en ``commit_form.yml`` : Follow
    l'exige dès le prochain commit. Réactiver la même entrée y reporte ses modifications."""
    require_role(user, slug, "editor")
    entry = _find(form_id)
    if entry.microproject not in (None, slug):
        raise NotFound(f"Formulaire d'intention {form_id!r} introuvable.")
    origin = {"form_id": entry.item.id, "name": entry.item.name}
    with keyed_lock("intent_forms.active", slug):
        _write_active(slug, entry.item.form, origin)
    return ActiveForm(entry.item.form, origin, False)


def deactivate(user: User, slug: str) -> None:
    require_role(user, slug, "editor")
    with keyed_lock("intent_forms.active", slug):
        _active_path(slug).unlink(missing_ok=True)


# --- migration des fichiers d'avant les identifiants --------------------------------------------

_LEGACY_SHARED = "formulaires_intention_partagees.json"
_LEGACY_OWN = "formulaires_intention.json"
_LEGACY_POINTER = "formulaire_intention_actif.json"


def _migrate_shelf(legacy: Path, target: Path) -> dict[str, str]:
    """Les entrées de ``legacy`` (indexées par nom) passent dans ``target`` (indexées par id) ;
    renvoie nom -> id. Rejouable : une entrée déjà migrée sous ce nom n'est pas dupliquée."""
    forms = _load(target)
    ids = {item.name: item.id for item in forms.values()}
    if legacy.exists():
        for name, raw in json.loads(legacy.read_text(encoding="utf-8")).get("forms", {}).items():
            if name in ids:
                continue
            item = IntentForm(id=secrets.token_hex(8), name=name, form=raw["form"], created_at=raw.get("created_at") or _now())
            forms[item.id] = item
            ids[name] = item.id
        _save(target, forms)
        legacy.unlink()
    return ids


def migrate_legacy_files(conn: sqlite3.Connection | None = None) -> None:
    """Migration ``0001_library_ids`` : les bibliothèques indexées par nom reçoivent des ids, et le
    pointeur ``formulaire_intention_actif.json`` devient l'en-tête d'origine de ``commit_form.yml``
    (le pointeur seul, sans ``commit_form.yml``, ne désignait plus rien et disparaît)."""
    root = data_dir()
    shared_ids = _migrate_shelf(root / _LEGACY_SHARED, root / LIBRARY_FILE)
    microprojects_root = root / "microprojects"
    for directory in sorted(microprojects_root.iterdir()) if microprojects_root.exists() else ():
        if not directory.is_dir():
            continue
        own_ids = _migrate_shelf(directory / _LEGACY_OWN, directory / LIBRARY_FILE)
        pointer = directory / _LEGACY_POINTER
        if not pointer.exists():
            continue
        active = directory / "follow" / ACTIVE_FILE
        if active.exists():
            target = json.loads(pointer.read_text(encoding="utf-8"))
            text = active.read_text(encoding="utf-8")
            form_id = (shared_ids if target.get("partagee") else own_ids).get(target.get("name"))
            if form_id is not None and _read_origin(text) is None:
                origin = {"form_id": form_id, "name": target["name"]}
                _write_atomically(active, f"{ORIGIN_MARK}{json.dumps(origin, ensure_ascii=False)}\n{text}")
        pointer.unlink()
