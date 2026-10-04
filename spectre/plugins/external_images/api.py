"""La route du plugin external_images, sous ``/api/microprojects/{microproject_slug}`` (la politique
des chemins est dans :mod:`.service`) :

- ``GET /external-images?directory=`` : les images d'un dossier autorisé, pour en choisir (éditeur).

Les images référencées par une mesure du cahier se lisent par l'entrée qui les porte (plugin
notebook, ``GET .../notebook-entries/{entry_id}/external-images/{index}``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["external-images"])


@router.get("/external-images")
def browse_external_images(directory: str, microproject: Microproject = Depends(require_role("editor"))) -> list[dict]:
    """Les images d'un dossier autorisé (503 si aucun dossier n'est autorisé sur ce serveur)."""
    return service.browse(directory)
