"""Un TIF du G4 rendu pour le navigateur, à la volée, sans copie sur disque : une vignette JPEG (la galerie) ou
l'image entière en PNG (la visionneuse, sans perte), d'une de ses trames (une par détecteur). Les octets rendus
restent en mémoire, bornés (:data:`THUMB_CACHE`, :data:`VIEW_CACHE`) et indexés par la date et la taille du
fichier : une image remplacée sur le partage est relue."""

from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import Any

from PIL import Image, ImageOps

from . import tiff_meta

THUMB_SIZE = 320
THUMB_CACHE = 1024  # ~25 Ko chacune
VIEW_CACHE = 24  # ~0,5 Mo chacune


def _stamp(path: str) -> tuple[int, int]:
    stat = os.stat(path)
    return stat.st_mtime_ns, stat.st_size


def _frame(image: Image.Image, frame: int) -> Image.Image:
    frames = getattr(image, "n_frames", 1)
    image.seek(max(0, min(frame, frames - 1)))
    if image.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        # 16 bits ou flottant : ramené sur 8 bits par ses extrêmes
        return ImageOps.autocontrast(image.convert("F").convert("L") if image.mode == "F" else image.point(lambda v: v / 256).convert("L"))
    return image.convert("L") if image.mode not in ("L", "RGB") else image.copy()


@lru_cache(maxsize=THUMB_CACHE)
def _thumbnail(path: str, stamp: tuple[int, int], frame: int) -> bytes:
    with Image.open(path) as image:
        picture = _frame(image, frame)
    picture.thumbnail((THUMB_SIZE, THUMB_SIZE))
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


@lru_cache(maxsize=VIEW_CACHE)
def _view(path: str, stamp: tuple[int, int], frame: int) -> bytes:
    with Image.open(path) as image:
        picture = _frame(image, frame)
    out = io.BytesIO()
    picture.save(out, "PNG", compress_level=3)
    return out.getvalue()


@lru_cache(maxsize=THUMB_CACHE)
def _meta(path: str, stamp: tuple[int, int]) -> dict[str, Any]:
    with Image.open(path) as image:
        tags = {key: image.tag_v2.get(key) for key in (tiff_meta.IMAGE_DESCRIPTION, tiff_meta.NEW_ADDITIONAL_INFORMATION)} if hasattr(image, "tag_v2") else {}
        return tiff_meta.describe(tags, image.size, getattr(image, "n_frames", 1))


def thumbnail(path: str, frame: int = 0) -> tuple[bytes, str]:
    """La vignette JPEG d'une trame et son étiquette (ETag)."""
    stamp = _stamp(path)
    return _thumbnail(path, stamp, frame), f"t{frame}-{stamp[0]:x}-{stamp[1]:x}"


def view(path: str, frame: int = 0) -> tuple[bytes, str]:
    """L'image entière d'une trame, en PNG, et son étiquette (ETag)."""
    stamp = _stamp(path)
    return _view(path, stamp, frame), f"v{frame}-{stamp[0]:x}-{stamp[1]:x}"


def meta(path: str) -> dict[str, Any]:
    """Les métadonnées du TIF (:func:`tiff_meta.describe`)."""
    return _meta(path, _stamp(path))
