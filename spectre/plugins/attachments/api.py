"""Fichiers téléversés d'un µprojet (:mod:`spectre.plugins.attachments.store`) : une image envoyée
avant la structure ou la preuve qui l'affichera, ses métadonnées et ses octets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import get_microproject, require_role
from ..microprojects.service import Microproject
from . import store

router = APIRouter(prefix="/api/microprojects/{microproject_slug}/attachments", tags=["attachments"])


def _member(min_role: str):
    """:func:`require_role` pour une route dont le paramètre de chemin est ``{microproject_slug}``.
    Transitoire : à remplacer par ``Depends(require_role(...))`` quand ``microprojects.deps`` lira
    ce paramètre (il lit encore ``{slug}``)."""
    check = require_role(min_role)

    def dependency(microproject_slug: str, user: User = Depends(current_user)) -> Microproject:
        return check(user=user, microproject=get_microproject(microproject_slug))

    return dependency


def _url(slug: str, attachment_id: str) -> str:
    return f"/api/microprojects/{slug}/attachments/{attachment_id}"


def _resource(slug: str, attachment: store.Attachment) -> dict:
    return {**attachment.as_dict(), "url": f"{_url(slug, attachment.id)}/content"}


@router.post("", status_code=201)
def upload_attachment(
    response: Response,
    file: UploadFile = File(...),
    purpose: str = Form(...),
    microproject: Microproject = Depends(_member("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Upload a file ahead of what will show it (``purpose`` : ``structure`` - a picture of a
    structure given as images - or ``evidence`` - a picture pasted in a preuve), so the page can
    show it straight from the server and the launch itself stays plain JSON. A file nothing ends
    up using just stays there, like a detached attachment."""
    attachment = store.save(
        microproject.slug, file.file, filename=file.filename, content_type=file.content_type, purpose=purpose, uploaded_by=user.name
    )
    response.headers["Location"] = _url(microproject.slug, attachment.id)
    return _resource(microproject.slug, attachment)


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, microproject: Microproject = Depends(_member("viewer"))) -> dict:
    attachment, _blob_path = store.get(microproject.slug, attachment_id)
    return _resource(microproject.slug, attachment)


def _safe_ascii_filename(name: str) -> str:
    """A best-effort ASCII fallback for Content-Disposition's ``filename=`` (the quoted-string
    form isn't reliably read as non-ASCII across browsers) - the real name, accents included,
    still round-trips through the metadata for display in the UI."""
    return name.encode("ascii", "ignore").decode("ascii").replace('"', "").strip() or "fichier"


@router.get("/{attachment_id}/content")
def get_attachment_content(attachment_id: str, microproject: Microproject = Depends(_member("viewer"))) -> FileResponse:
    """Serve an uploaded file's bytes directly off disk - scoped to the microproject it belongs
    to, not to an experiment version. Images are served inline so a page can use them directly as
    an ``<img src>``; everything else downloads."""
    attachment, blob_path = store.get(microproject.slug, attachment_id)
    headers = {"X-Content-Type-Options": "nosniff"}
    if not attachment.content_type.startswith("image/"):
        headers["Content-Disposition"] = f'attachment; filename="{_safe_ascii_filename(attachment.filename)}"'
    return FileResponse(blob_path, media_type=attachment.content_type, headers=headers)
