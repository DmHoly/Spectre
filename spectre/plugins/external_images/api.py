"""La galerie « DATA » d'une expérience : des images externes (mesures TEM, scans...) que Spectre
référence à leur emplacement d'origine sur le disque plutôt que de les copier - en créer une, en
retirer, changer l'image épinglée - et le parcours d'un dossier pour les choisir.
"""

from __future__ import annotations

import mimetypes
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...kernel.http import if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from ..experiments import service as experiments
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from ..structures import kinds

router = APIRouter(prefix="/api/microprojets", tags=["external-images"])


# Galerie "DATA" (Experiment.metadata["data_items"]) : images externes (mesures TEM, scans...) que
# Spectre référence à leur emplacement d'origine sur le disque plutôt que de copier, à la demande
# explicite de l'utilisateur. On lit ces fichiers directement, donc l'extension - pas un
# content-type fourni par un upload navigateur - est le seul signal disponible pour filtrer.
DATA_IMAGE_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


class DataSetInput(BaseModel):
    title: str | None = None
    note: str | None = None
    entity_index: int | None = None
    image_paths: list[str]
    pinned_index: int = 0


class DataPinRequest(BaseModel):
    pinned_index: int


def _validate_external_image_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise HTTPException(status_code=422, detail="le chemin doit être absolu")
    if not path.is_file():
        raise HTTPException(status_code=422, detail=f"fichier introuvable : {raw}")
    if path.suffix.lower() not in DATA_IMAGE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"type d'image non pris en charge : {path.suffix}")
    return path.resolve()


@router.post("/{slug}/experiences/{ref}/data", status_code=201)
def create_data_item(
    ref: str,
    body: DataSetInput,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Attach an external, live-referenced image gallery ("DATA") to this experiment or to one of
    its campaign variants - a "what I designed vs what I measured" comparison alongside the
    simulated structure drawing. Deliberately independent of the ``Evidence``/``kind`` mechanism:
    these images are never copied into Spectre's storage, just referenced by absolute path, so
    they can go stale if the file is later moved - that's accepted (see :func:`data_image`).
    """
    if not body.image_paths:
        raise HTTPException(status_code=422, detail="au moins une image est nécessaire")
    if body.pinned_index < 0 or body.pinned_index >= len(body.image_paths):
        raise HTTPException(status_code=422, detail="pinned_index hors limites")
    resolved_paths = [str(_validate_external_image_path(p)) for p in body.image_paths]
    record = {
        "id": f"data_{secrets.token_hex(10)}",
        "title": body.title,
        "note": body.note,
        "entity_index": body.entity_index,
        "image_paths": resolved_paths,
        "pinned_index": body.pinned_index,
        "created_by": user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    def change(builder: Any, parent: Any) -> None:
        if body.entity_index is not None:
            expected_count = kinds.entity_count(parent.structure_type, parent.structure)
            if body.entity_index < 0 or body.entity_index >= expected_count:
                raise HTTPException(status_code=422, detail="cette entité n'existe pas sur cette expérience")
        builder.metadata["data_items"] = list(builder.metadata.get("data_items", [])) + [record]

    experiment = experiments.amend(microproject.slug, ref, author=user.name, expected_version=if_match_version(if_match), change=change)
    return {"id": ref, "version_id": experiment.id, "data_item": record}


@router.delete("/{slug}/experiences/{ref}/data/{data_id}")
def remove_data_item(
    ref: str,
    data_id: str,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    def change(builder: Any, parent: Any) -> None:
        existing = parent.metadata.get("data_items", [])
        remaining = [d for d in existing if d.get("id") != data_id]
        if len(remaining) == len(existing):
            raise HTTPException(status_code=404, detail="donnée introuvable sur cette version")
        builder.metadata["data_items"] = remaining

    experiment = experiments.amend(microproject.slug, ref, author=user.name, expected_version=if_match_version(if_match), change=change)
    return {"id": ref, "version_id": experiment.id}


@router.patch("/{slug}/experiences/{ref}/data/{data_id}/epingle")
def pin_data_item(
    ref: str,
    data_id: str,
    body: DataPinRequest,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Cheap re-pin: swap which image within one already-created data item is the featured lead
    comparison image, without touching anything else about the item."""

    def change(builder: Any, parent: Any) -> None:
        existing = parent.metadata.get("data_items", [])
        target = next((d for d in existing if d.get("id") == data_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="donnée introuvable sur cette version")
        if body.pinned_index < 0 or body.pinned_index >= len(target.get("image_paths", [])):
            raise HTTPException(status_code=422, detail="pinned_index hors limites")
        builder.metadata["data_items"] = [dict(d, pinned_index=body.pinned_index) if d.get("id") == data_id else d for d in existing]

    experiment = experiments.amend(microproject.slug, ref, author=user.name, expected_version=if_match_version(if_match), change=change)
    return {"id": ref, "version_id": experiment.id}


@router.get("/{slug}/data/parcourir")
def browse_data_folder(dossier: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """List candidate images in an external folder (non-recursive) so the user can pick which
    ones to attach and which to pin, without Spectre ever copying the bytes."""
    path = Path(dossier)
    if not path.is_absolute() or not path.is_dir():
        raise HTTPException(status_code=422, detail="dossier introuvable ou chemin non absolu")
    images = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name):
        if entry.is_file() and entry.suffix.lower() in DATA_IMAGE_ALLOWED_EXTENSIONS:
            images.append({"name": entry.name, "path": str(entry.resolve()), "size": entry.stat().st_size})
    return {"images": images}


@router.get("/{slug}/data/image")
def data_image(chemin: str, microproject: Microproject = Depends(require_role("viewer"))) -> FileResponse:
    """Serve an external image referenced by an experience's DATA gallery directly off its
    original location. Since these paths are never copied and can go stale (file moved/deleted),
    any failure - missing file, bad extension, relative path - collapses to a plain 404 here
    rather than distinguishing why, so the frontend can show one clean "image introuvable"
    placeholder without needing to interpret the reason."""
    try:
        path = _validate_external_image_path(chemin)
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="fichier introuvable") from exc
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=media_type or "application/octet-stream")
