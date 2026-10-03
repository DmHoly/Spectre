"""Fichiers téléversés d'un µprojet : un blob plus un petit sidecar JSON (nom d'origine, type,
taille, usage, auteur, date) par fichier, rangés sous ``<dossier du µprojet>/attachments/`` et nommés
par un id frais (``att_<hex>``) plutôt que par le nom téléversé - rien ici n'a jamais à transformer
un nom fourni par l'utilisateur en chemin sûr.

Chaque fichier sert à quelque chose (:data:`PURPOSES`) : une image de structure, une image de preuve.
C'est l'usage qui fixe les types et la taille acceptés. Les sidecars plus anciens restent lisibles :
``role`` (``"structure"`` / ``"preuve"``) au lieu de ``purpose``, ou sans usage ni auteur du tout
(les pièces jointes d'une expérience).
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from ...kernel.errors import DomainError, InvalidInput, NotFound
from ..microprojects.service import microproject_dir

ATTACHMENT_ID_RE = re.compile(r"^att_[0-9a-f]{20}$")
CHUNK_BYTES = 1024 * 1024

# Types d'image acceptés pour une image téléversée (structure en image, image d'une preuve) : ce que
# le navigateur sait afficher tel quel (un TIFF de microscope ne l'est pas - le coller depuis le
# logiciel, ou l'exporter en PNG). image/svg+xml volontairement absent : un SVG peut embarquer du
# <script>, un vecteur XSS stocké classique pour un fichier destiné à être affiché tel quel.
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
IMAGE_MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Purpose:
    types: frozenset[str]
    max_bytes: int


# À quoi sert un fichier téléversé par POST .../attachments, et ce que cet usage accepte.
PURPOSES = {
    "structure": Purpose(IMAGE_TYPES, IMAGE_MAX_BYTES),
    "evidence": Purpose(IMAGE_TYPES, IMAGE_MAX_BYTES),
}

# Usage des sidecars écrits avant ``purpose`` (champ ``role``).
_LEGACY_ROLES = {"structure": "structure", "preuve": "evidence"}


class TooLarge(DomainError):
    """Un fichier plus gros que ce que son usage accepte."""

    status = 413
    code = "too_large"


@dataclass(frozen=True)
class Attachment:
    id: str
    filename: str
    content_type: str
    size: int
    purpose: str | None
    uploaded_by: str | None
    uploaded_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def attachments_dir(slug: str) -> Path:
    """Where uploaded files live for this microproject - one blob plus a small JSON sidecar per
    attachment, named by its id rather than the uploaded filename so nothing here ever has to
    sanitize that into a safe path.
    """
    path = microproject_dir(slug) / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_attachment_id() -> str:
    return f"att_{secrets.token_hex(10)}"


def _type_problem(content_type: str) -> str:
    if content_type in ("image/tiff", "image/tif", "image/bmp"):
        return "Format non affichable par le navigateur - copiez l'image depuis votre logiciel puis collez-la (Ctrl+V), ou exportez-la en PNG."
    return f"Type de fichier non pris en charge ({content_type or 'inconnu'}) : une image PNG, JPEG, GIF ou WebP."


def save(slug: str, stream: BinaryIO, *, filename: str | None, content_type: str | None, purpose: str, uploaded_by: str) -> Attachment:
    """Store an uploaded file for ``purpose`` - its type checked first, then its bytes copied to
    disk chunk by chunk and refused (:class:`TooLarge`) as soon as they pass the purpose's limit,
    never read into memory as a whole."""
    rules = PURPOSES.get(purpose)
    if rules is None:
        raise InvalidInput(f"Usage inconnu ({purpose or 'aucun'}) : {', '.join(PURPOSES)}.")
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type not in rules.types:
        raise InvalidInput(_type_problem(content_type))

    attachment_id = new_attachment_id()
    directory = attachments_dir(slug)
    blob_path = directory / attachment_id
    partial = directory / f"{attachment_id}.part"
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := stream.read(CHUNK_BYTES):
                size += len(chunk)
                if size > rules.max_bytes:
                    raise TooLarge(f"Fichier trop volumineux ({rules.max_bytes // (1024 * 1024)} Mo maximum).")
                out.write(chunk)
        if not size:
            raise InvalidInput("Fichier vide.")
        os.replace(partial, blob_path)
    finally:
        partial.unlink(missing_ok=True)

    attachment = Attachment(
        id=attachment_id,
        filename=(filename or "").strip() or "fichier",
        content_type=content_type,
        size=size,
        purpose=purpose,
        uploaded_by=uploaded_by,
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )
    sidecar = {key: value for key, value in attachment.as_dict().items() if key != "id"}
    (directory / f"{attachment_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return attachment


def _read(slug: str, attachment_id: str) -> tuple[Path, dict[str, Any]] | None:
    """``(blob path, sidecar)`` of one file of this microproject - ``None`` unless the id is
    well-formed and both files exist (the id is checked, never turned into a path otherwise)."""
    if not ATTACHMENT_ID_RE.fullmatch(attachment_id or ""):
        return None
    directory = attachments_dir(slug)
    blob_path = directory / attachment_id
    sidecar_path = directory / f"{attachment_id}.json"
    if not blob_path.is_file() or not sidecar_path.is_file():
        return None
    return blob_path, json.loads(sidecar_path.read_text(encoding="utf-8"))


def get(slug: str, attachment_id: str) -> tuple[Attachment, Path]:
    """One file of this microproject and where its bytes are, whatever sidecar format it was
    written in - :class:`NotFound` otherwise."""
    found = _read(slug, attachment_id)
    if found is None:
        raise NotFound("Pièce jointe introuvable.")
    blob_path, sidecar = found
    attachment = Attachment(
        id=attachment_id,
        filename=sidecar.get("filename") or "fichier",
        content_type=sidecar.get("content_type") or "application/octet-stream",
        size=sidecar.get("size", blob_path.stat().st_size),
        purpose=sidecar.get("purpose") or _LEGACY_ROLES.get(sidecar.get("role")),
        uploaded_by=sidecar.get("uploaded_by"),
        uploaded_at=sidecar.get("uploaded_at"),
    )
    return attachment, blob_path


def uploaded_image(slug: str, image_id: str) -> dict:
    """The sidecar (filename, content type, size...) of an image uploaded to *this* microproject -
    :class:`InvalidInput` unless the id really names one, checked against the files on disk, never
    turned into a path from anything else."""
    found = _read(slug, image_id)
    if found is None:
        raise InvalidInput("Image introuvable - collez-la ou choisissez-la à nouveau.")
    _blob_path, sidecar = found
    if sidecar.get("content_type") not in IMAGE_TYPES:
        raise InvalidInput("Ce fichier n'est pas une image affichable (PNG, JPEG, GIF ou WebP).")
    return sidecar
