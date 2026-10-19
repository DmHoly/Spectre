"""Les routes du plugin sem_images - les images MEB du G4 d'une plaque, lues sur le partage sans copie :

- ``GET /api/wafers/{wafer_key}/sem-images?fdl=&refresh=`` : les images de la plaque rangées par acquisition
  (:func:`.service.listing`), cherchées par ses FDL connues (vie en ligne, études) et celles de ``fdl`` (répété),
  plus l'index des dossiers de PRISM ;
- ``GET /api/wafers/{wafer_key}/sem-images/file?path=&variant=thumb|view&frame=`` : une image de cette liste,
  rendue pour le navigateur (vignette JPEG ou PNG entier, une trame = un détecteur) ; ETag et cache privé ;
- ``GET /api/wafers/{wafer_key}/sem-images/meta?path=`` : ce que le TIF dit de lui-même (champ de vue, taille du
  pixel, position sur le wafer, défaut revu, date) ;
- ``GET /api/sem-images/index`` : où en est l'index des dossiers ; ``POST /api/sem-images/index`` le met à jour en
  arrière-plan (``full=true`` : le reconstruit, administrateurs seulement).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from ...kernel.errors import Forbidden
from ..accounts.deps import current_user
from ..accounts.service import User
from . import render, service

router = APIRouter(prefix="/api", tags=["sem-images"])

MAX_FDLS = service.MAX_FDLS


def _fdls(user: User, lasermark: str, extra: list[str]) -> list[str]:
    """Les FDL où chercher : celles que la vie en ligne connaît à la plaque, celles de ses études, puis ``extra``."""
    return service.known_fdls(user, lasermark, extra)


@router.get("/wafers/{wafer_key}/sem-images")
def list_sem_images(
    wafer_key: str,
    fdl: list[str] = Query([], max_length=MAX_FDLS),
    refresh: bool = False,
    user: User = Depends(current_user),
) -> dict:
    """Les images MEB du G4 de la plaque, par acquisition (503 si le partage n'est pas monté ou PRISM trop ancien)."""
    return service.listing(wafer_key, _fdls(user, wafer_key, fdl), refresh=refresh)


def _cached(request: Request, body: bytes, etag: str, media_type: str) -> Response:
    tag = f'"{etag}"'
    headers = {"ETag": tag, "Cache-Control": "private, max-age=3600"}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=media_type, headers=headers)


@router.get("/wafers/{wafer_key}/sem-images/file")
def sem_image_file(
    request: Request,
    wafer_key: str,
    path: str = Query(..., max_length=1024),
    variant: str = Query("thumb", pattern="^(thumb|view)$"),
    frame: int = Query(0, ge=0, le=15),
    fdl: list[str] = Query([], max_length=MAX_FDLS),
    user: User = Depends(current_user),
) -> Response:
    """Une image de la plaque rendue pour le navigateur : ``thumb`` (JPEG, 320 px) ou ``view`` (PNG entier)."""
    file = service.image_path(wafer_key, path, lambda: _fdls(user, wafer_key, fdl))
    if variant == "thumb":
        body, etag = render.thumbnail(file, frame)
        return _cached(request, body, etag, "image/jpeg")
    body, etag = render.view(file, frame)
    return _cached(request, body, etag, "image/png")


@router.get("/wafers/{wafer_key}/sem-images/meta")
def sem_image_meta(
    wafer_key: str,
    path: str = Query(..., max_length=1024),
    fdl: list[str] = Query([], max_length=MAX_FDLS),
    user: User = Depends(current_user),
) -> dict:
    """Ce que le TIF dit de lui-même (:func:`.tiff_meta.describe`) et son chemin complet sur le partage."""
    file = service.image_path(wafer_key, path, lambda: _fdls(user, wafer_key, fdl))
    return {**render.meta(file), "file": file}


@router.get("/sem-images/index")
def sem_images_index(user: User = Depends(current_user)) -> dict:
    """Où en est l'index des dossiers d'images (:func:`.service.index_status`)."""
    return service.index_status()


@router.post("/sem-images/index")
def update_sem_images_index(full: bool = False, user: User = Depends(current_user)) -> JSONResponse:
    """Met l'index à jour en arrière-plan (202) ; ``full`` le reconstruit en entier (~2 minutes, administrateurs)."""
    if full and not user.is_admin:
        raise Forbidden("Reconstruire tout l'index est réservé aux administrateurs.", code="admin_only")
    service.source.require_root()
    started = service.start_index(full=full or not service.index_status()["exists"])
    return JSONResponse(status_code=202, content={**service.index_status(), "started": started})
