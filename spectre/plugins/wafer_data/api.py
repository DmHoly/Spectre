"""La fiche data des plaques.

- ``/api/areas/{area_slug}/wafer-data/...`` : les blocs qu'un projet corporate montre sur ses plaques
  (:mod:`.blocks`) - lire est ouvert à tout compte connecté, les changer et calculer d'avance les fiches du
  projet (``POST .../compute``) demandent de pouvoir gérer le projet ; de même pour lire les vraies colonnes
  d'un type de données sur ses plaques (``POST .../catalog/{hook}/probe``) et choisir le type d'une colonne
  (``PUT .../catalog/{hook}/columns``, qui vaut pour tous les projets : :mod:`.columns`) ;
- ``/api/wafers/{wafer_key}/data`` : la fiche data d'une plaque, bloc par bloc, pour chaque projet de ses
  µprojets (:func:`.service.sheet`) ; ``?refresh=true`` retape les bases ; ses images se lisent une à une
  (``.../data/images/{block_id}/{index}``) ;
- ``/api/wafer-data/catalog`` : le même catalogue hors de tout projet (les blocs libres d'une analyse de plaques),
  et ``.../catalog/{hook}/probe`` qui en lit les vraies colonnes sur une plaque donnée - tout compte connecté ;
- ``/api/wafer-data/storage`` : ce que pèse le magasin des résumés (administrateurs).
"""

from __future__ import annotations

from typing import Any, Literal

from dataclasses import asdict

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...kernel.errors import Forbidden, InvalidInput, NotFound
from ..accounts.deps import current_user
from ..accounts.service import User
from ..areas import service as areas
from . import blocks, columns, service, store

router = APIRouter(prefix="/api", tags=["wafer_data"])


class BlockRequest(BaseModel):
    kind: Literal["value", "histogram", "boxplot", "scatter", "wafermap", "curve", "images"]
    hook: str = Field("", max_length=80)
    config: dict[str, Any] = {}
    label: str | None = None


class UpdateBlockRequest(BaseModel):
    label: str | None = None  # vide : le nom par défaut
    config: dict[str, Any] | None = None  # remplace la config (même genre, même type de données)
    move: Literal["up", "down"] | None = None


class ColumnTypeRequest(BaseModel):
    column: str = Field(..., min_length=1, max_length=200)
    type: str | None = None  # None : revenir au type observé ou deviné


class ProbeRequest(BaseModel):
    lasermark: str | None = Field(None, max_length=80)  # sinon : quelques plaques suivies du projet


def _managed(area_slug: str, user: User) -> areas.ManagementArea:
    area = areas.get_by_slug(area_slug)
    areas.require_manage(user, area)
    return area


def _payload(block: blocks.Block, entries: dict[str, blocks.CatalogHook] | None = None) -> dict:
    entries = entries if entries is not None else {h.hook: h for h in blocks.catalog()}
    entry = entries.get(block.hook)
    return {
        "id": block.id,
        "kind": block.kind,
        "kind_label": blocks.KINDS[block.kind],
        "hook": block.hook,
        "hook_title": entry.title if entry else block.hook,
        "available": block.from_pattern or entry is not None,
        "config": block.config,
        "label": block.label,
        "title": block.title,
        "unit": block.unit(entry),
        "position": block.position,
        "created_at": block.created_at,
    }


def _hook(entry: blocks.CatalogHook) -> dict:
    return {**asdict(entry), "columns": list(entry.columns)}


def _catalog() -> dict:
    return {
        "hooks": [_hook(h) for h in blocks.catalog()],
        "types": [{"key": k, "label": v} for k, v in columns.TYPES.items()],
        "roles": {k: list(v) for k, v in columns.ROLES.items()},
        "kinds": [{"key": k, "label": v} for k, v in blocks.KINDS.items()],
        "aggregates": [{"key": k, "label": v} for k, v in blocks.AGGREGATE_LABELS.items()],
        "curve_modes": [{"key": k, "label": v} for k, v in blocks.CURVE_MODES.items()],
        "placeholders": list(blocks.PLACEHOLDERS),
        "limits": {"images": blocks.MAX_IMAGES, "pattern_images": blocks.MAX_PATTERN_IMAGES, "caption": blocks.MAX_CAPTION, "colors": blocks.COLORS},
    }


@router.get("/areas/{area_slug}/wafer-data/catalog")
def get_catalog(area_slug: str, user: User = Depends(current_user)) -> dict:
    """Ce qu'un bloc peut lire : les types de données PRISM par plaque et leurs colonnes typées (``type`` :
    choisi, sinon observé sur de vraies lignes, sinon deviné sur la fiche PRISM), les types de colonnes et ce
    que chaque usage accepte, les genres de bloc, les agrégats d'une valeur, les repères d'un modèle de chemin."""
    areas.get_by_slug(area_slug)
    return _catalog()


@router.get("/wafer-data/catalog")
def get_free_catalog(user: User = Depends(current_user)) -> dict:
    """Le même catalogue, hors de tout projet : pour les blocs libres d'une analyse de plaques."""
    return _catalog()


@router.post("/wafer-data/catalog/{hook}/probe")
def probe_free(hook: str, body: ProbeRequest, user: User = Depends(current_user)) -> dict:
    """Lit ``hook`` sur la plaque ``lasermark`` (requise) pour en observer les vraies colonnes ; rend le type à jour."""
    if not (body.lasermark or "").strip():
        raise InvalidInput("Indiquez une plaque sur laquelle lire les colonnes.", code="no_wafer_to_probe")
    return _hook(service.probe(None, user, hook, lasermark=body.lasermark))


@router.post("/areas/{area_slug}/wafer-data/catalog/{hook}/probe")
def probe_hook(area_slug: str, hook: str, body: ProbeRequest | None = None, user: User = Depends(current_user)) -> dict:
    """Lit ``hook`` sur une plaque (``lasermark``) ou quelques plaques suivies du projet pour en observer les
    vraies colonnes et leurs types ; rend le type de données à jour, comme dans le catalogue."""
    area = _managed(area_slug, user)
    return _hook(service.probe(area, user, hook, lasermark=body.lasermark if body else None))


@router.put("/areas/{area_slug}/wafer-data/catalog/{hook}/columns")
def set_column_type(area_slug: str, hook: str, body: ColumnTypeRequest, user: User = Depends(current_user)) -> dict:
    """Choisit le type d'une colonne (``type`` null : revenir au type observé ou deviné) - pour tous les
    projets ; rend le type de données à jour."""
    _managed(area_slug, user)
    entry = blocks.catalog_entry(hook)
    if entry is None:
        raise NotFound(f"« {hook} » n'est pas un type de données PRISM par plaque.")
    if body.column not in entry.names:
        raise InvalidInput(f"« {body.column} » n'est pas une colonne de « {entry.title} ».", code="unknown_column")
    columns.set_type(hook, body.column, body.type, user.id)
    return _hook(blocks.catalog_entry(hook))


@router.get("/areas/{area_slug}/wafer-data/blocks")
def list_blocks(area_slug: str, user: User = Depends(current_user)) -> list[dict]:
    area = areas.get_by_slug(area_slug)
    entries = {h.hook: h for h in blocks.catalog()}
    return [_payload(b, entries) for b in blocks.list_blocks(area)]


@router.post("/areas/{area_slug}/wafer-data/blocks", status_code=201)
def add_block(area_slug: str, body: BlockRequest, response: Response, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    block = blocks.add_block(area, user, body.kind, body.hook, body.config, body.label)
    response.headers["Location"] = f"/api/areas/{area.slug}/wafer-data/blocks/{block.id}"
    return _payload(block)


@router.patch("/areas/{area_slug}/wafer-data/blocks/{block_id}")
def update_block(area_slug: str, block_id: int, body: UpdateBlockRequest, user: User = Depends(current_user)) -> dict:
    area = _managed(area_slug, user)
    return _payload(blocks.update_block(area, block_id, label=body.label, config=body.config, move=body.move))


@router.delete("/areas/{area_slug}/wafer-data/blocks/{block_id}", status_code=204)
def remove_block(area_slug: str, block_id: int, user: User = Depends(current_user)) -> Response:
    blocks.remove_block(_managed(area_slug, user), block_id)
    return Response(status_code=204)


@router.post("/areas/{area_slug}/wafer-data/compute")
def compute_area(area_slug: str, offset: int = 0, refresh: bool = False, user: User = Depends(current_user)) -> dict:
    """Calcule d'avance les fiches d'un paquet de plaques du projet (celles qui manquent ; toutes avec
    ``refresh``) : ``{total, done, next_offset, computed, errors, source}`` - rappeler avec ``next_offset``."""
    return service.compute_area(_managed(area_slug, user), user, offset=max(offset, 0), refresh=refresh)


@router.get("/wafers/{wafer_key}/data")
def get_wafer_data(wafer_key: str, refresh: bool = False, user: User = Depends(current_user)) -> dict:
    """La fiche data d'une plaque : ``{wafer, source, areas: [{area, can_manage, microprojects, blocks}]}`` -
    ``areas`` vide pour une plaque qu'aucun µprojet ne suit. Un bloc : ``status`` (ok, empty, error), ``data``
    (son résumé), ``computed_at`` ; une valeur porte aussi ``population`` (les plaques du projet déjà calculées)."""
    return service.sheet(user, wafer_key, refresh=refresh)


@router.get("/wafers/{wafer_key}/data/images/{block_id}/{index}")
def get_wafer_image(wafer_key: str, block_id: int, index: int, user: User = Depends(current_user)) -> FileResponse:
    return FileResponse(service.image_file(user, wafer_key, block_id, index), headers={"Cache-Control": "private, max-age=3600"})


@router.get("/wafer-data/storage")
def get_storage(user: User = Depends(current_user)) -> dict:
    """Ce que pèse le magasin des résumés (``digests``, ``wafers``, ``scalars``, ``payload_bytes``,
    ``file_bytes``, ``budget_bytes``) - administrateurs."""
    if not user.is_admin:
        raise Forbidden("Réservé aux administrateurs.")
    return store.stats()
