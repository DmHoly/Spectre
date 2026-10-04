"""La politique des images externes : des fichiers (mesures TEM, scans...) que Spectre référence à
leur emplacement d'origine sur le disque du serveur plutôt que de les copier - une mesure manuelle du
cahier en porte (plugin notebook, qui les sert par identifiant), et l'éditeur les choisit en
parcourant un dossier (:func:`browse`).

Ces fichiers sont lus directement sur le disque du serveur, donc l'accès est borné :

- les racines autorisées sont celles de ``SPECTRE_EXTERNAL_IMAGE_ROOTS`` (dossiers séparés par
  ``os.pathsep``). Définies, tout chemin - à l'écriture d'une mesure, au parcours d'un dossier, à la
  lecture d'une image - doit s'y trouver, avant comme après résolution des liens ;
- sans elles, le parcours des dossiers est désactivé, et seul un chemin local est accepté ;
- un chemin hors des racines est refusé **sans toucher au disque** : sous Windows, la simple lecture
  d'un chemin réseau (UNC) déclenche une authentification SMB sortante ;
- une image se lit par l'entrée du cahier qui la référence et son rang : le chemin vient des
  métadonnées de l'étude, jamais de la requête (c'est au plugin notebook de s'en tenir là).
"""

from __future__ import annotations

import os
from pathlib import Path

from ...kernel.errors import Forbidden, InvalidInput, NotFound, Unavailable

ROOTS_ENV = "SPECTRE_EXTERNAL_IMAGE_ROOTS"
# On lit ces fichiers directement : l'extension est le seul signal disponible pour les filtrer.
DISPLAYABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
# Des images, mais que le navigateur n'affiche pas : refusées à l'écriture, signalées au parcours.
NOT_DISPLAYABLE = {".tif", ".tiff"}


def configured_roots() -> list[str]:
    """Les racines autorisées telles qu'écrites dans ``SPECTRE_EXTERNAL_IMAGE_ROOTS`` (absolues, sans
    doublon, sans toucher au disque) : les dossiers d'où partir pour choisir des images. Vide si la
    variable n'est pas définie (le parcours est alors désactivé)."""
    written: list[str] = []
    for raw in os.environ.get(ROOTS_ENV, "").split(os.pathsep):
        if raw.strip() and (path := os.path.abspath(raw.strip())) not in written:
            written.append(path)
    return written


def roots() -> list[Path] | None:
    """Les racines autorisées (``SPECTRE_EXTERNAL_IMAGE_ROOTS``), telles qu'écrites et résolues (un
    nom court Windows, un lien...), ou ``None`` si la variable n'est pas définie."""
    allowed: list[Path] = []
    for raw in configured_roots():
        allowed += [Path(raw), Path(raw).resolve()]
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
    n'affiche pas) ou ``forbidden`` (hors des dossiers autorisés) - pour une image référencée."""
    try:
        path = _resolve(raw)
    except Forbidden:
        return "forbidden"
    except InvalidInput:
        return "missing"
    if path.suffix.lower() not in DISPLAYABLE:
        return "unsupported"
    return "ok" if path.is_file() else "missing"


def checked_image(raw: str) -> str:
    """Le chemin, résolu, d'une image qu'on peut référencer : sous les racines, dans un format que
    le navigateur affiche (un TIFF est refusé avec la marche à suivre), et présente sur le disque."""
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


def readable_file(raw: str) -> Path:
    """Le fichier d'une image référencée, à servir - revérifié à chaque lecture : une image d'avant
    ces règles qui pointe hors des racines est refusée (403), un format que le navigateur n'affiche
    pas aussi (422), un fichier déplacé ou supprimé est un 404."""
    path = _resolve(raw)
    if path.suffix.lower() not in DISPLAYABLE:
        raise InvalidInput("Format d'image que le navigateur ne sait pas afficher.", code="unsupported_format")
    if not path.is_file():
        raise NotFound("Image introuvable : le fichier a été déplacé ou supprimé.", code="image_missing")
    return path


def browse(directory: str) -> list[dict]:
    """Les images d'un dossier autorisé (sans descendre dans ses sous-dossiers), TIFF compris mais
    signalés (``displayable``) - pour choisir celles d'une mesure sans rien copier."""
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
