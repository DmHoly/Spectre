"""Fichiers téléversés d'un µprojet : un blob plus un petit sidecar JSON (nom d'origine, type,
taille...) par fichier, rangés sous ``<dossier du µprojet>/attachments/`` et nommés par un id frais
(``att_<hex>``) plutôt que par le nom téléversé - rien ici n'a jamais à transformer un nom fourni
par l'utilisateur en chemin sûr.
"""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..microprojects.service import microproject_dir

ATTACHMENT_ID_RE = re.compile(r"^att_[0-9a-f]{20}$")

# Pièces jointes : mesure, wafer map, photo, rapport - assez large pour couvrir ces cas sans ouvrir
# la porte à n'importe quel type de fichier. image/svg+xml volontairement absent : un SVG peut
# embarquer du <script>, un vecteur XSS stocké classique pour un fichier destiné à être affiché tel
# quel dans le navigateur.
ATTACHMENT_ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/csv",
    "text/plain",
}
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024

# Types d'image acceptés pour une image téléversée (structure en image, image d'une preuve) : ce que
# le navigateur sait afficher tel quel (un TIFF de microscope ne l'est pas - le coller depuis le
# logiciel, ou l'exporter en PNG). image/svg+xml volontairement absent, comme pour les pièces jointes.
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
IMAGE_MAX_BYTES = 10 * 1024 * 1024


def attachments_dir(slug: str) -> Path:
    """Where uploaded files live for this microproject - one blob plus a small JSON sidecar
    (original filename/content type/size) per attachment, named by its id rather than the uploaded
    filename so nothing here ever has to sanitize that into a safe path.
    """
    path = microproject_dir(slug) / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_attachment_id() -> str:
    return f"att_{secrets.token_hex(10)}"


def write(slug: str, attachment_id: str, contents: bytes, sidecar: dict[str, Any]) -> None:
    directory = attachments_dir(slug)
    (directory / attachment_id).write_bytes(contents)
    (directory / f"{attachment_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def remove(slug: str, attachment_id: str) -> None:
    directory = attachments_dir(slug)
    (directory / attachment_id).unlink(missing_ok=True)
    (directory / f"{attachment_id}.json").unlink(missing_ok=True)


def read(slug: str, attachment_id: str) -> tuple[Path, dict[str, Any]] | None:
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


def uploaded_image(slug: str, image_id: str) -> dict:
    """The sidecar (filename, content type, size...) of an image uploaded to *this* microproject
    (``POST /images`` or ``/structures/images``) - 422 unless the id really names one, checked
    against the files on disk, never turned into a path from anything else."""
    found = read(slug, image_id)
    if found is None:
        raise HTTPException(status_code=422, detail="Image introuvable - collez-la ou choisissez-la à nouveau.")
    _blob_path, sidecar = found
    if sidecar.get("content_type") not in IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="Ce fichier n'est pas une image affichable (PNG, JPEG, GIF ou WebP).")
    return sidecar
