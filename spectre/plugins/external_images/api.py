"""Les routes du plugin external_images, sous ``/api/microprojects/{microproject_slug}`` (la politique
des chemins est dans :mod:`.service`) :

- ``GET /external-images?directory=`` : les images d'un dossier autorisé, pour en choisir (éditeur) ;
  chacune avec l'``url`` de son aperçu ;
- ``GET /external-images/file?path=`` : les octets d'une image d'un dossier autorisé, pour la voir
  avant de l'épingler (le carrousel de l'éditeur ; 503 si le parcours est désactivé) ;
- ``GET /external-images/roots`` : les dossiers autorisés, d'où partir (éditeur ; vide : parcours
  désactivé).

Les images référencées par une mesure du cahier se lisent par l'entrée qui les porte (plugin
notebook, ``GET .../notebook-entries/{entry_id}/external-images/{index}``).
"""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["external-images"])


@router.get("/external-images")
def browse_external_images(directory: str, microproject: Microproject = Depends(require_role("editor"))) -> list[dict]:
    """Les images d'un dossier autorisé (503 si aucun dossier n'est autorisé sur ce serveur)."""
    base = f"/api/microprojects/{quote(microproject.slug)}/external-images/file?path="
    return [{**image, "url": base + quote(image["path"], safe="")} for image in service.browse(directory)]


@router.get("/external-images/file")
def preview_external_image(path: str, microproject: Microproject = Depends(require_role("editor"))) -> FileResponse:
    """Une image d'un dossier autorisé, à voir avant de l'épingler à une mesure."""
    file = service.preview_file(path)
    media_type, _ = mimetypes.guess_type(file.name)
    return FileResponse(file, media_type=media_type or "application/octet-stream")


@router.get("/external-images/roots")
def external_image_roots(microproject: Microproject = Depends(require_role("editor"))) -> list[str]:
    """Les dossiers autorisés (``SPECTRE_EXTERNAL_IMAGE_ROOTS``, tels qu'écrits) d'où partir pour
    choisir des images ; une liste vide : le parcours est désactivé sur ce serveur."""
    return service.configured_roots()
