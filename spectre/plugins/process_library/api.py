"""Les trois bibliothèques, en collections à plat : ``/api/saved-structures``, ``/api/step-presets``
et ``/api/tech-bricks`` (lister, créer, lire, modifier, supprimer). Des routes explicites par
ressource - leurs modèles diffèrent - qui délèguent au service commun (:mod:`.service`)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from structureforge.process.steps import ProcessStep

from ..accounts import service as accounts
from ..accounts.deps import current_user
from ..accounts.service import User
from ..structures import simulation
from . import service
from .service import SAVED_STRUCTURES, STEP_PRESETS, TECH_BRICKS, Collection, Entry
from .step_presets import StepPresetPayload
from .structure_library import ExperimentOrigin

router = APIRouter(prefix="/api", tags=["process-library"])

WritableScope = Literal["shared", "microproject"]


class _NewItem(BaseModel):
    name: str
    scope: WritableScope
    microproject: str | None = None


class _ItemChanges(BaseModel):
    name: str | None = None
    scope: WritableScope | None = None
    microproject: str | None = None


class NewSavedStructure(_NewItem):
    substrate: simulation.SubstrateSpec
    steps: list[ProcessStep]
    declared_params: dict[str, list[simulation.DeclaredParam]] = {}
    layer_labels: dict[str, simulation.LayerLabel] = {}
    bricks: list[simulation.ProcessBrick] = []
    recipes: simulation.ProcessRecipes = Field(default_factory=simulation.ProcessRecipes)
    derived_from: str | ExperimentOrigin | None = None


class SavedStructureChanges(_ItemChanges):
    substrate: simulation.SubstrateSpec | None = None
    steps: list[ProcessStep] | None = None
    declared_params: dict[str, list[simulation.DeclaredParam]] | None = None
    layer_labels: dict[str, simulation.LayerLabel] | None = None
    bricks: list[simulation.ProcessBrick] | None = None
    recipes: simulation.ProcessRecipes | None = None


class NewStepPreset(_NewItem):
    payload: StepPresetPayload
    notes: str | None = None


class StepPresetChanges(_ItemChanges):
    payload: StepPresetPayload | None = None
    notes: str | None = None


class NewTechBrick(_NewItem):
    # le nom que reprend la brique d'un procédé où on l'insère (ProcessBrick) : la même limite
    name: str = Field(max_length=simulation.BRICK_NAME_MAX_LENGTH)
    steps: list[ProcessStep]
    declared_params: dict[str, list[simulation.DeclaredParam]] = {}
    layer_labels: dict[str, simulation.LayerLabel] = {}
    bricks: list[simulation.ProcessBrick] = []
    recipes: simulation.ProcessRecipes = Field(default_factory=simulation.ProcessRecipes)
    notes: str | None = None


class TechBrickChanges(_ItemChanges):
    name: str | None = Field(None, max_length=simulation.BRICK_NAME_MAX_LENGTH)
    steps: list[ProcessStep] | None = None
    declared_params: dict[str, list[simulation.DeclaredParam]] | None = None
    layer_labels: dict[str, simulation.LayerLabel] | None = None
    bricks: list[simulation.ProcessBrick] | None = None
    recipes: simulation.ProcessRecipes | None = None
    notes: str | None = None


def _content(body: BaseModel) -> dict[str, Any]:
    """Les champs envoyés, sans la portée ; les paramètres déclarés (et les étiquettes de couches,
    qui suivent la même règle) rangés par indice d'étape."""
    fields = body.model_dump(mode="json", exclude_unset=True, exclude={"scope", "microproject"})
    declared = getattr(body, "declared_params", None)
    if declared is not None:
        fields["declared_params"] = simulation.declared_params_json(simulation.declared_params_by_index(declared))
    return fields


def _changes(body: _ItemChanges) -> dict[str, Any]:
    return {**_content(body), **body.model_dump(exclude_unset=True, include={"scope", "microproject"})}


class _Serializer:
    """Un élément tel que l'API le rend : ses champs, sa portée, ses auteurs (id et nom) et si le
    demandeur peut le modifier. Les noms des comptes sont lus une fois par réponse."""

    def __init__(self, user: User):
        self.user = user
        self._names: dict[int, str | None] = {}

    def _account(self, user_id: int | None) -> dict[str, Any] | None:
        if user_id is None:
            return None
        if user_id not in self._names:
            account = accounts.get_by_id(user_id)
            self._names[user_id] = account.name if account else None
        return {"id": user_id, "name": self._names[user_id]}

    def __call__(self, entry: Entry) -> dict[str, Any]:
        return {
            **entry.item.model_dump(mode="json"),
            "scope": entry.scope,
            "microproject": entry.microproject.slug if entry.microproject else None,
            "created_by": self._account(entry.item.created_by),
            "updated_by": self._account(entry.item.updated_by),
            "can_edit": service.can_edit(entry, self.user),
        }


def _list(collection: Collection, user: User, microproject: str | None, scope: str | None) -> list[dict[str, Any]]:
    serialize = _Serializer(user)
    return [serialize(entry) for entry in service.list_items(collection, user, microproject_slug=microproject, scope=scope)]


def _create(collection: Collection, body: _NewItem, user: User, response: Response) -> dict[str, Any]:
    entry = service.create_item(collection, user, _content(body), scope=body.scope, microproject_slug=body.microproject)
    response.headers["Location"] = f"/api/{collection.key}/{entry.item.id}"
    return _Serializer(user)(entry)


# -- structures enregistrées -----------------------------------------------------------------------


@router.get("/saved-structures")
def list_saved_structures(microproject: str | None = None, scope: str | None = None, user: User = Depends(current_user)) -> list[dict[str, Any]]:
    return _list(SAVED_STRUCTURES, user, microproject, scope)


@router.post("/saved-structures", status_code=201)
def create_saved_structure(body: NewSavedStructure, response: Response, user: User = Depends(current_user)) -> dict[str, Any]:
    return _create(SAVED_STRUCTURES, body, user, response)


@router.get("/saved-structures/{structure_id}")
def get_saved_structure(structure_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.get_item(SAVED_STRUCTURES, user, structure_id))


@router.patch("/saved-structures/{structure_id}")
def update_saved_structure(structure_id: str, body: SavedStructureChanges, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.update_item(SAVED_STRUCTURES, user, structure_id, _changes(body)))


@router.delete("/saved-structures/{structure_id}", status_code=204, response_class=Response)
def delete_saved_structure(structure_id: str, user: User = Depends(current_user)) -> None:
    service.delete_item(SAVED_STRUCTURES, user, structure_id)


# -- présets d'étape -------------------------------------------------------------------------------


@router.get("/step-presets")
def list_step_presets(microproject: str | None = None, scope: str | None = None, user: User = Depends(current_user)) -> list[dict[str, Any]]:
    return _list(STEP_PRESETS, user, microproject, scope)


@router.post("/step-presets", status_code=201)
def create_step_preset(body: NewStepPreset, response: Response, user: User = Depends(current_user)) -> dict[str, Any]:
    return _create(STEP_PRESETS, body, user, response)


@router.get("/step-presets/{preset_id}")
def get_step_preset(preset_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.get_item(STEP_PRESETS, user, preset_id))


@router.patch("/step-presets/{preset_id}")
def update_step_preset(preset_id: str, body: StepPresetChanges, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.update_item(STEP_PRESETS, user, preset_id, _changes(body)))


@router.delete("/step-presets/{preset_id}", status_code=204, response_class=Response)
def delete_step_preset(preset_id: str, user: User = Depends(current_user)) -> None:
    service.delete_item(STEP_PRESETS, user, preset_id)


# -- briques technologiques ------------------------------------------------------------------------


@router.get("/tech-bricks")
def list_tech_bricks(microproject: str | None = None, scope: str | None = None, user: User = Depends(current_user)) -> list[dict[str, Any]]:
    return _list(TECH_BRICKS, user, microproject, scope)


@router.post("/tech-bricks", status_code=201)
def create_tech_brick(body: NewTechBrick, response: Response, user: User = Depends(current_user)) -> dict[str, Any]:
    return _create(TECH_BRICKS, body, user, response)


@router.get("/tech-bricks/{brick_id}")
def get_tech_brick(brick_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.get_item(TECH_BRICKS, user, brick_id))


@router.patch("/tech-bricks/{brick_id}")
def update_tech_brick(brick_id: str, body: TechBrickChanges, user: User = Depends(current_user)) -> dict[str, Any]:
    return _Serializer(user)(service.update_item(TECH_BRICKS, user, brick_id, _changes(body)))


@router.delete("/tech-bricks/{brick_id}", status_code=204, response_class=Response)
def delete_tech_brick(brick_id: str, user: User = Depends(current_user)) -> None:
    service.delete_item(TECH_BRICKS, user, brick_id)
