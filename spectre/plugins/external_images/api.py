"""Les routes de la galerie d'images externes, sous ``/api/microprojects/{microproject_slug}`` (le
domaine, et les règles d'accès au disque, sont dans :mod:`.service`) :

- ``GET /experiments/{experiment_id}/image-sets`` : les jeux d'images (``?version=`` pour une version
  passée), chaque image avec son ``status`` et son ``url`` ; ``POST``, ``PATCH`` (``pinned_index``) et
  ``DELETE`` les créent, changent l'image épinglée et les retirent - chaque fois une écriture sur la
  piste, avec ``If-Match`` (412 si elle a avancé), et l'``ETag`` de la nouvelle version en réponse.
- ``GET .../image-sets/{set_id}/images/{index}`` : les octets d'une image, lue à son emplacement
  d'origine (le chemin vient des métadonnées de l'étude, jamais de la requête).
- ``GET /external-images?directory=`` : les images d'un dossier autorisé, pour en choisir (éditeur).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import FileResponse

from ...kernel.http import etag, if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import get_microproject, require_role
from ..microprojects.service import Microproject
from . import service
from .schemas import ImageSetInput, ImageSetUpdate

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["external-images"])


def _member(min_role: str):
    """:func:`require_role` pour une route dont le paramètre de chemin est ``{microproject_slug}``.
    Transitoire : à remplacer par ``Depends(require_role(...))`` quand ``microprojects.deps`` lira
    ce paramètre (il lit encore ``{slug}``)."""
    check = require_role(min_role)

    def dependency(microproject_slug: str, user: User = Depends(current_user)) -> Microproject:
        return check(user=user, microproject=get_microproject(microproject_slug))

    return dependency


def _resource(slug: str, experiment_id: str, item: dict, version: str | None = None) -> dict:
    """Un jeu d'images tel que l'API le montre : chaque image avec son état et l'URL de ses octets
    (``?version=`` quand le jeu est lu sur une version passée)."""
    base = f"/api/microprojects/{slug}/experiments/{experiment_id}/image-sets/{item['id']}/images"
    query = f"?version={quote(version)}" if version else ""
    return {
        "id": item["id"],
        "title": item.get("title"),
        "note": item.get("note"),
        "entity_index": item.get("entity_index"),
        "pinned_index": item.get("pinned_index", 0),
        "created_by": item.get("created_by"),
        "created_at": item.get("created_at"),
        "images": [
            {"index": i, "name": Path(path).name, "path": path, "status": service.image_status(path), "url": f"{base}/{i}{query}"}
            for i, path in enumerate(item.get("image_paths", []))
        ],
    }


@router.get("/experiments/{experiment_id}/image-sets")
def list_image_sets(experiment_id: str, version: str | None = None, microproject: Microproject = Depends(_member("viewer"))) -> list[dict]:
    return [_resource(microproject.slug, experiment_id, item, version) for item in service.image_sets(microproject.slug, experiment_id, version)]


@router.post("/experiments/{experiment_id}/image-sets", status_code=201)
def create_image_set(
    experiment_id: str,
    body: ImageSetInput,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(_member("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Un jeu d'images de plus - sans ``Location`` : un jeu n'a pas de route de lecture propre, il se
    lit dans la galerie."""
    item, tip = service.create(microproject.slug, experiment_id, body, author=user.name, expected_version=if_match_version(if_match))
    response.headers["ETag"] = etag(tip.id)
    return _resource(microproject.slug, experiment_id, item)


@router.patch("/experiments/{experiment_id}/image-sets/{set_id}")
def update_image_set(
    experiment_id: str,
    set_id: str,
    body: ImageSetUpdate,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(_member("editor")),
    user: User = Depends(current_user),
) -> dict:
    item, tip = service.pin(
        microproject.slug, experiment_id, set_id, body.pinned_index, author=user.name, expected_version=if_match_version(if_match)
    )
    response.headers["ETag"] = etag(tip.id)
    return _resource(microproject.slug, experiment_id, item)


@router.delete("/experiments/{experiment_id}/image-sets/{set_id}", status_code=204)
def delete_image_set(
    experiment_id: str,
    set_id: str,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(_member("editor")),
    user: User = Depends(current_user),
) -> Response:
    tip = service.remove(microproject.slug, experiment_id, set_id, author=user.name, expected_version=if_match_version(if_match))
    return Response(status_code=204, headers={"ETag": etag(tip.id)})


@router.get("/experiments/{experiment_id}/image-sets/{set_id}/images/{index}")
def get_image(
    experiment_id: str, set_id: str, index: int, version: str | None = None, microproject: Microproject = Depends(_member("viewer"))
) -> FileResponse:
    path = service.image_file(microproject.slug, experiment_id, set_id, index, version)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.get("/external-images")
def browse_external_images(directory: str, microproject: Microproject = Depends(_member("editor"))) -> list[dict]:
    """Les images d'un dossier autorisé (503 si aucun dossier n'est autorisé sur ce serveur)."""
    return service.browse(directory)
