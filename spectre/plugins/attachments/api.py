"""Fichiers téléversés d'un µprojet (:mod:`spectre.plugins.attachments.store`) : une image envoyée
avant la preuve ou la structure qui l'affichera, et le service des octets de tout fichier du µprojet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import store

router = APIRouter(prefix="/api/microprojets", tags=["attachments"])


@router.post("/{slug}/images", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Upload a picture ahead of the preuve that will show it (pasted or dropped in the preuve
    form) - same storage and rules as :func:`upload_structure_image`."""
    return await _store_uploaded_image(file, microproject, user, role="preuve")


@router.post("/{slug}/structures/images", status_code=201)
async def upload_structure_image(
    file: UploadFile = File(...),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Upload one picture of a structure (pasted, dropped or picked on the « structure en image »
    page, or when changing the pictures on a fiche) ahead of the launch that will use it - so the
    page can show it straight from the server and the launch itself stays plain JSON. Stored like
    an attachment (blob + JSON sidecar named by a fresh id, see
    :func:`spectre.plugins.attachments.store.attachments_dir`), served by the same
    ``/pieces-jointes/{id}`` route. A picture no launch ends up using just stays there, like a
    detached attachment."""
    return await _store_uploaded_image(file, microproject, user, role="structure")


async def _store_uploaded_image(file: UploadFile, microproject: Microproject, user: User, *, role: str) -> dict:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in store.IMAGE_TYPES:
        if content_type in ("image/tiff", "image/tif", "image/bmp"):
            detail = "Format non affichable par le navigateur - copiez l'image depuis votre logiciel puis collez-la (Ctrl+V), ou exportez-la en PNG."
        else:
            detail = f"Type de fichier non pris en charge ({content_type or 'inconnu'}) : une image PNG, JPEG, GIF ou WebP."
        raise HTTPException(status_code=422, detail=detail)
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Image vide.")
    if len(contents) > store.IMAGE_MAX_BYTES:
        raise HTTPException(status_code=422, detail="Image trop volumineuse (10 Mo maximum).")

    image_id = store.new_attachment_id()
    filename = (file.filename or "structure").strip() or "structure"
    sidecar = {
        "filename": filename,
        "content_type": content_type,
        "size": len(contents),
        "role": role,
        "uploaded_by": user.name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    store.write(microproject.slug, image_id, contents, sidecar)
    return {
        "image_id": image_id,
        "url": f"/api/microprojets/{microproject.slug}/pieces-jointes/{image_id}",
        "filename": filename,
        "content_type": content_type,
        "size": len(contents),
    }


def _safe_ascii_filename(name: str) -> str:
    """A best-effort ASCII fallback for Content-Disposition's ``filename=`` (the quoted-string
    form isn't reliably read as non-ASCII across browsers) - the real name, accents included,
    still round-trips through the JSON sidecar for display in the UI."""
    return name.encode("ascii", "ignore").decode("ascii").strip() or "fichier"


@router.get("/{slug}/pieces-jointes/{attachment_id}")
def download_attachment(attachment_id: str, microproject: Microproject = Depends(require_role("viewer"))) -> FileResponse:
    """Serve an uploaded file's bytes directly off disk - deliberately not scoped to a specific
    experience version (an attachment's identity as a file doesn't depend on which commit still
    lists it), just to the microproject it belongs to. Images are served inline so a preview can use
    them directly as an ``<img src>``; everything else downloads.
    """
    found = store.read(microproject.slug, attachment_id)
    if found is None:
        raise HTTPException(status_code=404, detail="pièce jointe introuvable")
    blob_path, sidecar = found
    content_type = sidecar.get("content_type", "application/octet-stream")
    headers = {}
    if not content_type.startswith("image/"):
        headers["Content-Disposition"] = f'attachment; filename="{_safe_ascii_filename(sidecar.get("filename", "fichier"))}"'
    return FileResponse(blob_path, media_type=content_type, headers=headers)
