"""Routes des formulaires d'intention : la bibliothèque (``/api/intent-forms``, à plat, avec la
portée de chaque entrée) et le formulaire actif d'un µprojet
(``/api/microprojects/{microproject_slug}/active-intent-form``, lu dans ``commit_form.yml``). Le
domaine et les droits sont dans :mod:`spectre.plugins.intent_forms.service`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..accounts.deps import current_user
from ..accounts.service import User
from . import service as intent_forms
from .service import ActiveForm, LibraryEntry

router = APIRouter(prefix="/api", tags=["intent-forms"])


class CreateIntentFormRequest(BaseModel):
    name: str
    yaml: str
    scope: str  # shared | microproject
    microproject: str | None = None


class UpdateIntentFormRequest(BaseModel):
    name: str | None = None
    yaml: str | None = None


class ActivateIntentFormRequest(BaseModel):
    intent_form_id: str


def _account(user_id: int | None, name: str | None) -> dict | None:
    """``{id, name}`` comme dans process_library, ou ``None`` pour une entrée d'avant cette trace."""
    return None if user_id is None and name is None else {"id": user_id, "name": name}


def _entry_payload(entry: LibraryEntry, user: User) -> dict:
    item = entry.item
    return {
        "id": item.id,
        "name": item.name,
        "scope": entry.scope,
        "microproject": entry.microproject,
        "created_by": _account(item.created_by_id, item.created_by),
        "updated_by": _account(item.updated_by_id, item.updated_by),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "can_edit": intent_forms.can_edit(user, entry),
        "form": item.form.model_dump(mode="json"),
    }


def _active_payload(active: ActiveForm) -> dict:
    return {"form": active.form.model_dump(mode="json"), "origin": active.origin, "outdated": active.outdated}


@router.get("/intent-forms")
def list_intent_forms(microproject: str | None = None, scope: str | None = None, user: User = Depends(current_user)) -> list[dict]:
    return [_entry_payload(entry, user) for entry in intent_forms.list_forms(user, microproject=microproject, scope=scope)]


@router.post("/intent-forms", status_code=201)
def create_intent_form(body: CreateIntentFormRequest, response: Response, user: User = Depends(current_user)) -> dict:
    entry = intent_forms.create_form(user, name=body.name, yaml_text=body.yaml, scope=body.scope, microproject=body.microproject)
    response.headers["Location"] = f"/api/intent-forms/{entry.item.id}"
    return _entry_payload(entry, user)


@router.get("/intent-forms/{form_id}")
def get_intent_form(form_id: str, user: User = Depends(current_user)) -> dict:
    return _entry_payload(intent_forms.get_form(user, form_id), user)


@router.patch("/intent-forms/{form_id}")
def update_intent_form(form_id: str, body: UpdateIntentFormRequest, user: User = Depends(current_user)) -> dict:
    changes = body.model_dump(exclude_unset=True)
    entry = intent_forms.update_form(user, form_id, name=changes.get("name"), yaml_text=changes.get("yaml"))
    return _entry_payload(entry, user)


@router.delete("/intent-forms/{form_id}", status_code=204)
def delete_intent_form(form_id: str, user: User = Depends(current_user)) -> Response:
    intent_forms.delete_form(user, form_id)
    return Response(status_code=204)


@router.get("/microprojects/{microproject_slug}/active-intent-form", response_model=None, responses={204: {"description": "Aucun formulaire actif"}})
def get_active_intent_form(microproject_slug: str, user: User = Depends(current_user)) -> dict | Response:
    """Le formulaire actif ; ``204`` sans corps si le µprojet n'en a pas : un singleton absent est
    un état normal, pas une erreur (``ARCHITECTURE.md`` § 5)."""
    active = intent_forms.get_active(user, microproject_slug)
    if active is None:
        return Response(status_code=204)
    return _active_payload(active)


@router.put("/microprojects/{microproject_slug}/active-intent-form")
def set_active_intent_form(microproject_slug: str, body: ActivateIntentFormRequest, user: User = Depends(current_user)) -> dict:
    return _active_payload(intent_forms.activate(user, microproject_slug, body.intent_form_id))


@router.delete("/microprojects/{microproject_slug}/active-intent-form", status_code=204)
def delete_active_intent_form(microproject_slug: str, user: User = Depends(current_user)) -> Response:
    intent_forms.deactivate(user, microproject_slug)
    return Response(status_code=204)
