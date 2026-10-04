"""Les routes du cahier de données, sous ``/api/microprojects/{microproject_slug}`` (le domaine est
dans :mod:`.service`, :mod:`.legacy` et :mod:`.snapshots`) :

- ``POST /snapshots`` : charger un type de données de caractérisation pour des plaques et le figer ;
  ``GET /snapshots/{snapshot_id}`` le relit (un instantané ne change jamais : il se met en cache).
- ``GET /experiments/{experiment_id}/notebook-entries`` : le cahier d'une étude (``?version=`` pour
  une version passée ; filtres ``?step=`` (un id d'étape), ``?wafer=`` (une plaque), ``?kind=`` ;
  ``?summary=steps`` : le nombre d'entrées par étape, ``{step_id: n}``, pour les badges du procédé) ;
  ``POST`` y ajoute une entrée (201 + ``Location``), ``GET``, ``PATCH`` et ``DELETE`` sur
  ``/{entry_id}`` la lisent, la modifient (``position`` pour la déplacer) et la retirent (204). Chaque
  écriture est une écriture sur la piste, avec ``If-Match`` (412 si elle a avancé) ; chaque réponse
  porte l'``ETag`` de la version lue ou écrite.
- ``GET .../notebook-entries/{entry_id}/external-images/{index}`` : les octets d'une image externe
  qu'une mesure manuelle de l'entrée référence (``index`` : son rang dans l'entrée, ``?version=``
  pour une version passée), lue à son emplacement d'origine - le chemin vient du cahier, jamais de
  la requête, et la politique du plugin external_images s'applique à chaque lecture.

Les types de données qu'on peut charger se lisent dans le catalogue de caractérisation
(``GET /api/characterization/data-types?by_wafer=true&status=implemented``) ; les fichiers d'une
entrée manuelle se téléversent d'abord (``POST .../attachments``, ``purpose=notebook``).
"""

from __future__ import annotations

import mimetypes
from typing import Literal

import follow
from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import FileResponse

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


def _tag(response: Response, version: follow.Experiment) -> None:
    """L'``ETag`` de la version de la piste lue ou écrite : ce qu'une écriture suivante attend."""
    response.headers["ETag"] = etag(version.id)


def _entries_url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}/notebook-entries"


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
def list_entries(
    experiment_id: str,
    response: Response,
    version: str | None = None,
    step: str | None = None,
    wafer: str | None = None,
    kind: Literal["prism", "manual"] | None = None,
    summary: Literal["steps"] | None = None,
    microproject: Microproject = Depends(require_role("viewer")),
) -> list[dict] | dict[str, int]:
    """Les entrées du cahier (de la version ``version``), filtrées - ou, avec ``summary=steps``, le
    nombre d'entrées qui s'appliquent à cette version par étape."""
    if summary == "steps":
        read, counts = service.step_counts(microproject.slug, experiment_id, version, step=step, wafer=wafer, kind=kind)
        _tag(response, read)
        return counts
    read, items = service.entries(microproject.slug, experiment_id, version, step=step, wafer=wafer, kind=kind)
    _tag(response, read)
    return items


@router.post("/experiments/{experiment_id}/notebook-entries", status_code=201)
def add_entry(
    experiment_id: str,
    body: EntryInput,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Une entrée de plus en fin de cahier : une nouvelle version de la piste."""
    written, entry = service.add_entry(microproject.slug, experiment_id, body, author=user.name, expected_version=if_match_version(if_match))
    created(response, f"{_entries_url(microproject.slug, experiment_id)}/{entry['id']}")
    _tag(response, written)
    return entry


@router.get("/experiments/{experiment_id}/notebook-entries/{entry_id}")
def get_entry(
    experiment_id: str, entry_id: str, response: Response, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> dict:
    read, entry = service.get_entry(microproject.slug, experiment_id, entry_id, version)
    _tag(response, read)
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
    written, entry = service.update_entry(
        microproject.slug, experiment_id, entry_id, body, author=user.name, expected_version=if_match_version(if_match)
    )
    _tag(response, written)
    return entry


@router.delete("/experiments/{experiment_id}/notebook-entries/{entry_id}", status_code=204)
def remove_entry(
    experiment_id: str,
    entry_id: str,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> Response:
    written = service.remove_entry(microproject.slug, experiment_id, entry_id, author=user.name, expected_version=if_match_version(if_match))
    return Response(status_code=204, headers={"ETag": etag(written.id)})


@router.get("/experiments/{experiment_id}/notebook-entries/{entry_id}/external-images/{index}")
def get_external_image(
    experiment_id: str, entry_id: str, index: int, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> FileResponse:
    path = service.external_image_file(microproject.slug, experiment_id, entry_id, index, version)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")
