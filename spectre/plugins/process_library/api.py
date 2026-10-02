"""The process library: saved structures, step presets and technology bricks - each in three
buckets (built-in, shared between microprojects, a microproject's own), with the same list/create/
update/delete routes over a :class:`~spectre.kernel.json_store.KeyedJsonStore`
(:mod:`spectre.kernel.scoped`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from structureforge.process.steps import ProcessStep

from ...kernel.scoped import list_three_buckets, reject_duplicate, require_existing
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from ..structures import simulation
from . import stores
from .step_presets import StepPreset, StepPresetPayload, default_step_presets
from .structure_library import SavedStructure, default_structure_presets
from .tech_bricks import TechBrick, default_tech_bricks

router = APIRouter(prefix="/api/microprojets", tags=["process-library"])


class StepPresetInput(BaseModel):
    name: str
    payload: StepPresetPayload
    notes: str | None = None
    partagee: bool = False


def _step_preset_store(microproject: Microproject, partagee: bool):
    return stores.get_shared_step_preset_store() if partagee else stores.get_step_preset_store(microproject.slug)


def _step_preset_payload(preset: StepPreset, scope: str) -> dict:
    return {**preset.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/presets-etapes")
def list_step_presets(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        stores.get_step_preset_store(microproject.slug),
        stores.get_shared_step_preset_store(),
        default_step_presets(),
        _step_preset_payload,
    )


@router.post("/{slug}/presets-etapes", status_code=201)
def create_step_preset(body: StepPresetInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _step_preset_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Un préset nommé {body.name!r} existe déjà dans cette bibliothèque.")
    preset = StepPreset(
        name=body.name,
        payload=body.payload,
        notes=body.notes,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(preset)
    return list_step_presets(microproject)


@router.put("/{slug}/presets-etapes/{name}")
def update_step_preset(
    name: str, body: StepPresetInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _step_preset_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Préset {name!r} introuvable.")
    preset = StepPreset(name=body.name, payload=body.payload, notes=body.notes, created_at=existing.created_at)
    store.rename(name, preset)
    return list_step_presets(microproject)


@router.delete("/{slug}/presets-etapes/{name}")
def delete_step_preset(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _step_preset_store(microproject, partagee).remove(name)
    return list_step_presets(microproject)


class SavedStructureInput(BaseModel):
    name: str
    substrate: simulation.SubstrateSpec
    steps: list[ProcessStep]
    declared_params: dict[str, list[simulation.DeclaredParam]] = {}
    derived_from: str | None = None
    partagee: bool = False


def _saved_structure_store(microproject: Microproject, partagee: bool):
    return stores.get_shared_structure_store() if partagee else stores.get_structure_store(microproject.slug)


def _saved_structure_payload(structure: SavedStructure, scope: str) -> dict:
    return {**structure.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/structures-sauvegardees")
def list_saved_structures(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        stores.get_structure_store(microproject.slug),
        stores.get_shared_structure_store(),
        default_structure_presets(),
        _saved_structure_payload,
    )


@router.post("/{slug}/structures-sauvegardees", status_code=201)
def create_saved_structure(body: SavedStructureInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _saved_structure_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Une structure nommée {body.name!r} existe déjà dans cette bibliothèque.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        declared_params=simulation.declared_params_json(simulation.declared_params_by_index(body.declared_params)),
        derived_from=body.derived_from,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(saved)
    return list_saved_structures(microproject)


@router.put("/{slug}/structures-sauvegardees/{name}")
def update_saved_structure(
    name: str, body: SavedStructureInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _saved_structure_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Structure {name!r} introuvable.")
    saved = SavedStructure(
        name=body.name,
        substrate=body.substrate,
        steps=body.steps,
        declared_params=simulation.declared_params_json(simulation.declared_params_by_index(body.declared_params)),
        derived_from=existing.derived_from,
        created_at=existing.created_at,
    )
    store.rename(name, saved)
    return list_saved_structures(microproject)


@router.delete("/{slug}/structures-sauvegardees/{name}")
def delete_saved_structure(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _saved_structure_store(microproject, partagee).remove(name)
    return list_saved_structures(microproject)


class TechBrickInput(BaseModel):
    name: str
    steps: list[ProcessStep]
    declared_params: dict[str, list[simulation.DeclaredParam]] = {}
    notes: str | None = None
    partagee: bool = False


def _tech_brick_store(microproject: Microproject, partagee: bool):
    return stores.get_shared_tech_brick_store() if partagee else stores.get_tech_brick_store(microproject.slug)


def _tech_brick_payload(brick: TechBrick, scope: str) -> dict:
    return {**brick.model_dump(mode="json"), "scope": scope}


@router.get("/{slug}/briques-technologiques")
def list_tech_bricks(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return list_three_buckets(
        stores.get_tech_brick_store(microproject.slug),
        stores.get_shared_tech_brick_store(),
        default_tech_bricks(),
        _tech_brick_payload,
    )


@router.post("/{slug}/briques-technologiques", status_code=201)
def create_tech_brick(body: TechBrickInput, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    store = _tech_brick_store(microproject, body.partagee)
    reject_duplicate(store, body.name, message=f"Une brique nommée {body.name!r} existe déjà dans cette bibliothèque.")
    brick = TechBrick(
        name=body.name,
        steps=body.steps,
        declared_params=simulation.declared_params_json(simulation.declared_params_by_index(body.declared_params)),
        notes=body.notes,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.upsert(brick)
    return list_tech_bricks(microproject)


@router.put("/{slug}/briques-technologiques/{name}")
def update_tech_brick(
    name: str, body: TechBrickInput, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))
) -> dict:
    store = _tech_brick_store(microproject, partagee)
    existing = require_existing(store, name, message=f"Brique {name!r} introuvable.")
    brick = TechBrick(
        name=body.name,
        steps=body.steps,
        declared_params=simulation.declared_params_json(simulation.declared_params_by_index(body.declared_params)),
        notes=body.notes,
        created_at=existing.created_at,
    )
    store.rename(name, brick)
    return list_tech_bricks(microproject)


@router.delete("/{slug}/briques-technologiques/{name}")
def delete_tech_brick(name: str, partagee: bool = False, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    _tech_brick_store(microproject, partagee).remove(name)
    return list_tech_bricks(microproject)
