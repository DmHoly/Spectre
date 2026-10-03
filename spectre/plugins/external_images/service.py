"""La galerie d'images externes d'une étude : des jeux d'images (mesures TEM, scans...) que Spectre
référence à leur emplacement d'origine plutôt que de les copier, rangés dans les métadonnées de
l'étude (:data:`IMAGE_SETS_KEY`), chacun avec son image épinglée - la comparaison « conçu / mesuré »
à côté de la structure simulée.

Ces fichiers sont lus directement sur le disque du serveur, donc l'accès est borné :

- les racines autorisées sont celles de ``SPECTRE_EXTERNAL_IMAGE_ROOTS`` (dossiers séparés par
  ``os.pathsep``). Définies, tout chemin - à la création d'un jeu, au parcours d'un dossier, à la
  lecture d'une image - doit s'y trouver, avant comme après résolution des liens ;
- sans elles, le parcours des dossiers est désactivé, et seul un chemin local est accepté ;
- un chemin hors des racines est refusé **sans toucher au disque** : sous Windows, la simple lecture
  d'un chemin réseau (UNC) déclenche une authentification SMB sortante ;
- une image se lit par son jeu et son rang : le chemin vient des métadonnées de l'étude, jamais de
  la requête.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import follow

from ...kernel.errors import Forbidden, InvalidInput, NotFound, Unavailable
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from ..structures import kinds
from .schemas import ImageSetInput

ROOTS_ENV = "SPECTRE_EXTERNAL_IMAGE_ROOTS"
IMAGE_SETS_KEY = "data_items"
# On lit ces fichiers directement : l'extension est le seul signal disponible pour les filtrer.
DISPLAYABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
# Des images, mais que le navigateur n'affiche pas : refusées à la création, signalées au parcours.
NOT_DISPLAYABLE = {".tif", ".tiff"}


def roots() -> list[Path] | None:
    """Les racines autorisées (``SPECTRE_EXTERNAL_IMAGE_ROOTS``), telles qu'écrites et résolues (un
    nom court Windows, un lien...), ou ``None`` si la variable n'est pas définie."""
    allowed: list[Path] = []
    for raw in os.environ.get(ROOTS_ENV, "").split(os.pathsep):
        if raw.strip():
            allowed += [Path(os.path.abspath(raw.strip())), Path(raw.strip()).resolve()]
    return allowed or None


def _inside(path: Path, allowed: list[Path]) -> bool:
    return any(path.is_relative_to(root) for root in allowed)


def _resolve(raw: str) -> Path:
    """Le chemin ``raw``, résolu, s'il est permis (:class:`Forbidden` sinon) - le disque n'est touché
    qu'une fois le chemin reconnu dans les racines."""
    path = Path(os.path.normpath(raw or "."))
    if not path.is_absolute():
        raise InvalidInput("Le chemin doit être absolu.", code="relative_path")
    allowed = roots()
    if allowed is None:
        if path.drive.startswith(("\\\\", "//")):
            raise Forbidden("Un chemin réseau n'est accepté que sous un dossier autorisé.", code="outside_roots")
        return path.resolve()
    if not _inside(path, allowed) or not _inside(resolved := path.resolve(), allowed):
        raise Forbidden("Ce chemin n'est pas dans un dossier autorisé pour les images externes.", code="outside_roots")
    return resolved


def image_status(raw: str) -> str:
    """``ok``, ``missing`` (déplacée ou supprimée), ``unsupported`` (format que le navigateur
    n'affiche pas) ou ``forbidden`` (hors des dossiers autorisés) - pour une image d'un jeu."""
    try:
        path = _resolve(raw)
    except Forbidden:
        return "forbidden"
    except InvalidInput:
        return "missing"
    if path.suffix.lower() not in DISPLAYABLE:
        return "unsupported"
    return "ok" if path.is_file() else "missing"


def _checked_image(raw: str) -> str:
    path = _resolve(raw)
    suffix = path.suffix.lower()
    if suffix in NOT_DISPLAYABLE:
        raise InvalidInput(
            f"« {path.name} » est une image TIFF, que le navigateur ne sait pas afficher : exportez-la en PNG ou en JPEG.",
            code="unsupported_format",
        )
    if suffix not in DISPLAYABLE:
        raise InvalidInput(f"« {path.name} » n'est pas une image (PNG, JPEG, GIF, WebP ou BMP).", code="not_an_image")
    if not path.is_file():
        raise InvalidInput(f"Fichier introuvable : {raw}", code="file_not_found")
    return str(path)


def browse(directory: str) -> list[dict]:
    """Les images d'un dossier autorisé (sans descendre dans ses sous-dossiers), TIFF compris mais
    signalés (``displayable``) - pour choisir celles d'un jeu sans rien copier."""
    if roots() is None:
        raise Unavailable(
            f"Le parcours des dossiers est désactivé sur ce serveur ({ROOTS_ENV} n'est pas défini).", code="browsing_disabled"
        )
    path = _resolve(directory)
    if not path.is_dir():
        raise NotFound("Dossier introuvable.", code="directory_not_found")
    return [
        {"name": entry.name, "path": str(entry), "size": entry.stat().st_size, "displayable": entry.suffix.lower() in DISPLAYABLE}
        for entry in sorted(path.iterdir(), key=lambda p: p.name.lower())
        if entry.suffix.lower() in DISPLAYABLE | NOT_DISPLAYABLE and entry.is_file()
    ]


def image_sets(slug: str, experiment_id: str, version_id: str | None = None) -> list[dict]:
    """Les jeux d'images d'une version de la piste (sa pointe par défaut)."""
    version = experiments.version_of(get_repository(slug), experiment_id, version_id)
    return list(version.metadata.get(IMAGE_SETS_KEY, []))


def _find(sets: list[dict], set_id: str) -> dict:
    found = next((item for item in sets if item.get("id") == set_id), None)
    if found is None:
        raise NotFound("Jeu d'images introuvable sur cette étude.", code="image_set_not_found")
    return found


def _check_pinned(pinned_index: int, count: int) -> None:
    if not 0 <= pinned_index < count:
        raise InvalidInput("L'image épinglée doit être l'une des images du jeu.", code="pinned_index_out_of_range")


def image_file(slug: str, experiment_id: str, set_id: str, index: int, version_id: str | None = None) -> Path:
    """Le fichier de l'image ``index`` du jeu ``set_id`` - son chemin lu dans les métadonnées."""
    paths = _find(image_sets(slug, experiment_id, version_id), set_id).get("image_paths", [])
    if not 0 <= index < len(paths):
        raise NotFound("Image introuvable dans ce jeu.", code="image_not_found")
    path = _resolve(paths[index])
    if path.suffix.lower() not in DISPLAYABLE:
        raise InvalidInput("Format d'image que le navigateur ne sait pas afficher.", code="unsupported_format")
    if not path.is_file():
        raise NotFound("Image introuvable : le fichier a été déplacé ou supprimé.", code="image_missing")
    return path


def create(slug: str, experiment_id: str, body: ImageSetInput, *, author: str, expected_version: str | None) -> tuple[dict, follow.Experiment]:
    """Un nouveau jeu d'images, pour toute l'étude ou pour une variante d'une campagne
    (``entity_index``) - renvoie le jeu et la nouvelle pointe."""
    if not body.image_paths:
        raise InvalidInput("Au moins une image est nécessaire.")
    _check_pinned(body.pinned_index, len(body.image_paths))
    record = {
        "id": f"data_{secrets.token_hex(10)}",
        "title": body.title,
        "note": body.note,
        "entity_index": body.entity_index,
        "image_paths": [_checked_image(raw) for raw in body.image_paths],
        "pinned_index": body.pinned_index,
        "created_by": author,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        if body.entity_index is not None and not 0 <= body.entity_index < kinds.entity_count(parent.structure_type, parent.structure):
            raise InvalidInput("Cette variante n'existe pas sur cette étude.", code="entity_not_found")
        builder.metadata[IMAGE_SETS_KEY] = [*parent.metadata.get(IMAGE_SETS_KEY, []), record]

    tip = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return record, tip


def pin(slug: str, experiment_id: str, set_id: str, pinned_index: int, *, author: str, expected_version: str | None) -> tuple[dict, follow.Experiment]:
    """Épingle une autre image du jeu (rien d'autre ne change) - renvoie le jeu et la pointe."""
    result: dict[str, Any] = {}

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        sets = parent.metadata.get(IMAGE_SETS_KEY, [])
        target = _find(sets, set_id)
        _check_pinned(pinned_index, len(target.get("image_paths", [])))
        result.update(target, pinned_index=pinned_index)
        builder.metadata[IMAGE_SETS_KEY] = [result if item is target else item for item in sets]

    tip = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return result, tip


def remove(slug: str, experiment_id: str, set_id: str, *, author: str, expected_version: str | None) -> follow.Experiment:
    """Retire un jeu de la galerie (il reste dans l'historique de l'étude ; les fichiers ne sont pas touchés)."""

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        sets = parent.metadata.get(IMAGE_SETS_KEY, [])
        target = _find(sets, set_id)
        builder.metadata[IMAGE_SETS_KEY] = [item for item in sets if item is not target]

    return experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
