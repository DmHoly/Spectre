"""Les routes du cahier de données, sous ``/api/microprojects/{microproject_slug}`` (le domaine est
dans :mod:`.service` et :mod:`.snapshots`) :

- ``POST /snapshots`` : charger un type de données de caractérisation pour des plaques et le figer ;
  ``GET /snapshots/{snapshot_id}`` le relit (un instantané ne change jamais : il se met en cache).
- ``GET /experiments/{experiment_id}/notebook-entries`` : les vues du cahier (``?version=`` pour une
  version passée) ; ``POST``, ``PATCH`` et ``DELETE`` les ajoutent, les modifient (``position``
  pour les déplacer) et les retirent - chaque fois une écriture sur la piste, avec ``If-Match``
  (412 si elle a avancé), et l'``ETag`` de la nouvelle version dans la réponse.

Les types de données qu'on peut charger se lisent dans le catalogue de caractérisation
(``GET /api/characterization/data-types?by_wafer=true&status=implemented``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response

from ...kernel.http import created, etag, if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service, snapshots
from .schemas import EntryInput, EntryUpdate, SnapshotRequest

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["notebook"])

# Un instantané ne change jamais (un nouvel id à chaque chargement) : le navigateur le garde.
IMMUTABLE = "private, max-age=31536000, immutable"


@router.post("/snapshots", status_code=201)
def take_snapshot(body: SnapshotRequest, response: Response, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    dataset = snapshots.fetch(body.hook, body.wafers, refresh=body.refresh)
    snapshot_id = snapshots.store(microproject.slug, dataset)
    created(response, f"/api/microprojects/{microproject.slug}/snapshots/{snapshot_id}")
    return {"snapshot_id": snapshot_id, **dataset}


@router.get("/snapshots/{snapshot_id}")
def read_snapshot(snapshot_id: str, response: Response, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    dataset = snapshots.load(microproject.slug, snapshot_id)
    response.headers["Cache-Control"] = IMMUTABLE
    return {"snapshot_id": snapshot_id, **dataset}


@router.get("/experiments/{experiment_id}/notebook-entries")
def list_entries(experiment_id: str, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    return service.entries(microproject.slug, experiment_id, version)


@router.post("/experiments/{experiment_id}/notebook-entries", status_code=201)
def add_entry(
    experiment_id: str,
    body: EntryInput,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Une vue de plus en fin de cahier - sans ``Location`` : une vue n'a pas de route de lecture
    propre, elle se lit dans le cahier."""
    entry, tip = service.add_entry(microproject.slug, experiment_id, body, author=user.name, expected_version=if_match_version(if_match))
    response.headers["ETag"] = etag(tip.id)
    return entry


@router.patch("/experiments/{experiment_id}/notebook-entries/{entry_id}")
def update_entry(
    experiment_id: str,
    entry_id: str,
    body: EntryUpdate,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    entry, tip = service.update_entry(
        microproject.slug, experiment_id, entry_id, body, author=user.name, expected_version=if_match_version(if_match)
    )
    response.headers["ETag"] = etag(tip.id)
    return entry


@router.delete("/experiments/{experiment_id}/notebook-entries/{entry_id}", status_code=204)
def remove_entry(
    experiment_id: str,
    entry_id: str,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> Response:
    tip = service.remove_entry(microproject.slug, experiment_id, entry_id, author=user.name, expected_version=if_match_version(if_match))
    return Response(status_code=204, headers={"ETag": etag(tip.id)})
