"""Online editor for the root library's YAML files (``library/*.yml`` - materials, recipes, step
presets, tech bricks, the intention-form copy). Until now these were only editable by hand on the
server (see ``library/README.md``); this exposes the same five files as raw-YAML text a user can
read and save from the browser, with the exact same validation the app already applies when it
*reads* them (:func:`spectre.core.registry.validate_library_yaml`) run *before* writing, so a bad
save fails loudly instead of silently falling back to the built-in defaults on the next reload.

Reserved to admins: unlike a µprojet's own "partagé"/"projet" presets and bricks
(:mod:`spectre.api.keyed_resource`), this is the one truly global, shared-by-everyone tier - a
mistake here is visible to every µprojet at once.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import registry
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api/bibliotheque", tags=["bibliotheque"])

# key (used in the URL) -> (filename in library/, title, one-line description shown on its card).
# Order here is the display order on the page.
LIBRARY_FILES: dict[str, dict[str, str]] = {
    "materiaux": {
        "filename": "materiaux.yml",
        "title": "Matériaux",
        "description": "La liste proposée dans le sélecteur de matériau du constructeur de structure (nom, catégorie, couleur...).",
    },
    "recettes": {
        "filename": "recettes.yml",
        "title": "Recettes",
        "description": "Recettes de dépôt/gravure supplémentaires (dont les gravures sélectives), fusionnées avec celles de StructureForge.",
    },
    "presets": {
        "filename": "presets.yml",
        "title": "Présets d'étape",
        "description": "Raccourcis nommés vers une recette de dépôt ou de gravure, proposés dans le formulaire d'étape.",
    },
    "briques": {
        "filename": "briques.yml",
        "title": "Briques technologiques",
        "description": "Séquences d'étapes réutilisables (masque + gravure, empilement de croissance...) insérables d'un bloc.",
    },
    "intention": {
        "filename": "intention.yml",
        "title": "Formulaire d'intention",
        "description": "Les libellés, placeholders et couleurs de la section « Objectifs et intention » du constructeur de structure.",
    },
}


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="réservé aux administrateurs")


def _meta_or_404(key: str) -> dict[str, str]:
    meta = LIBRARY_FILES.get(key)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"fichier de bibliothèque inconnu : {key!r}")
    return meta


class SaveLibraryFileRequest(BaseModel):
    content: str


@router.get("/fichiers")
def list_library_files(user: User = Depends(get_current_user)) -> dict:
    return {
        "files": [
            {"key": key, "filename": meta["filename"], "title": meta["title"], "description": meta["description"]}
            for key, meta in LIBRARY_FILES.items()
        ],
        "can_edit": user.is_admin,
    }


@router.get("/fichiers/{key}")
def get_library_file(key: str, user: User = Depends(get_current_user)) -> dict:
    meta = _meta_or_404(key)
    path = registry.library_dir() / meta["filename"]
    try:
        content = path.read_text(encoding="utf-8")
        exists = True
    except OSError:
        content = ""
        exists = False
    return {
        "key": key,
        "filename": meta["filename"],
        "title": meta["title"],
        "description": meta["description"],
        "content": content,
        "exists": exists,
        "can_edit": user.is_admin,
    }


@router.put("/fichiers/{key}")
def save_library_file(key: str, body: SaveLibraryFileRequest, user: User = Depends(get_current_user)) -> dict:
    _require_admin(user)
    meta = _meta_or_404(key)
    try:
        registry.validate_library_yaml(meta["filename"], body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = registry.library_dir() / meta["filename"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}
