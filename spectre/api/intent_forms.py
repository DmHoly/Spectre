"""Formulaires d'intention : la bibliothèque (spectre.core.intent_forms) et laquelle est active
pour un projet. Comme les présets d'étapes/structures sauvegardées/briques technologiques, deux
étagères par bibliothèque (partagée entre projets, propre au projet) plus les mêmes trois routes de
lecture/écriture (spectre.api.keyed_resource) - la seule différence est qu'un projet choisit aussi
une entrée comme *active*, ce qui matérialise son contenu dans le dépôt Follow du projet
(``commit_form.yml`` - voir spectre.core.projects.activate_intent_form) plutôt que de rester une
simple entrée de bibliothèque parmi d'autres.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from follow.storage.commit_form import CommitForm
from pydantic import BaseModel

from ..core import projects
from ..core.intent_forms import IntentForm, parse_yaml_form
from ..core.permissions import require_role
from ..core.projects import Project
from .keyed_resource import list_three_buckets, reject_duplicate, require_existing

router = APIRouter(prefix="/api/microprojets", tags=["intent-forms"])


class IntentFormInput(BaseModel):
    name: str
    yaml: str
    partagee: bool = False


def _intent_form_store(project: Project, partagee: bool):
    return projects.get_shared_intent_form_store() if partagee else projects.get_intent_form_store(project.slug)


def _intent_form_payload(entry: IntentForm, scope: str) -> dict:
    return {
        "name": entry.name,
        "form": entry.form.model_dump(mode="json"),
        "created_at": entry.created_at,
        "scope": scope,
    }


def _parse_or_422(text: str) -> CommitForm:
    try:
        return parse_yaml_form(text)
    except Exception as exc:  # invalid YAML, or a CommitForm/FormField that fails validation
        raise HTTPException(status_code=422, detail=f"Fichier de formulaire invalide : {exc}") from exc


@router.get("/{slug}/formulaires-intention")
def list_intent_forms(project: Project = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        projects.get_intent_form_store(project.slug),
        projects.get_shared_intent_form_store(),
        {},  # no built-in intent forms - a team's questions are always its own
        _intent_form_payload,
    )


@router.post("/{slug}/formulaires-intention", status_code=201)
def create_intent_form(body: IntentFormInput, project: Project = Depends(require_role("editor"))) -> dict:
    form = _parse_or_422(body.yaml)
    store = _intent_form_store(project, body.partagee)
    reject_duplicate(store, body.name, message=f"Un formulaire nommé {body.name!r} existe déjà dans cette bibliothèque.")
    entry = IntentForm(name=body.name, form=form, created_at=datetime.now(timezone.utc).isoformat())
    store.upsert(entry)
    return list_intent_forms(project)


@router.put("/{slug}/formulaires-intention/{name}")
def update_intent_form(
    name: str, body: IntentFormInput, partagee: bool = False, project: Project = Depends(require_role("editor"))
) -> dict:
    form = _parse_or_422(body.yaml)
    store = _intent_form_store(project, partagee)
    existing = require_existing(store, name, message=f"Formulaire {name!r} introuvable.")
    entry = IntentForm(name=body.name, form=form, created_at=existing.created_at)
    store.rename(name, entry)
    return list_intent_forms(project)


@router.delete("/{slug}/formulaires-intention/{name}")
def delete_intent_form(name: str, partagee: bool = False, project: Project = Depends(require_role("editor"))) -> dict:
    _intent_form_store(project, partagee).remove(name)
    active = projects.get_active_intent_form(project.slug)
    if active is not None and active["name"] == name and active["partagee"] == partagee:
        # the form this project was actively requiring just disappeared from the library it came
        # from - deactivate rather than leave commit_form.yml pointing at a name nothing lists
        # anymore (the file itself stays valid either way, but the settings page couldn't offer
        # "edit this" or explain where it came from once its library entry is gone).
        projects.deactivate_intent_form(project.slug)
    return list_intent_forms(project)


@router.get("/{slug}/formulaire-actif")
def get_active_intent_form(project: Project = Depends(require_role("viewer"))) -> dict | None:
    active = projects.get_active_intent_form(project.slug)
    if active is None:
        return None
    store = projects.get_shared_intent_form_store() if active["partagee"] else projects.get_intent_form_store(project.slug)
    entry = store.load_items().get(active["name"])
    if entry is None:
        return None
    return _intent_form_payload(entry, "partagee" if active["partagee"] else "projet")


class ActivateIntentFormRequest(BaseModel):
    name: str | None = None
    partagee: bool = False


@router.post("/{slug}/formulaire-actif")
def set_active_intent_form(body: ActivateIntentFormRequest, project: Project = Depends(require_role("editor"))) -> dict | None:
    if body.name is None:
        projects.deactivate_intent_form(project.slug)
        return None
    store = _intent_form_store(project, body.partagee)
    entry = require_existing(store, body.name, message=f"Formulaire {body.name!r} introuvable.")
    projects.activate_intent_form(project.slug, name=entry.name, partagee=body.partagee, form=entry.form)
    return _intent_form_payload(entry, "partagee" if body.partagee else "projet")
