"""Les fichiers YAML de la bibliothèque racine, lisibles par tout compte connecté et modifiables par
un administrateur (un changement ici se voit dans tous les µprojets à la fois), et les textes
d'interface qui en sont tirés."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..accounts.deps import current_user, require_admin
from ..accounts.service import User
from . import service
from .service import LibraryFile

router = APIRouter(prefix="/api", tags=["library"])


class LibraryFileContent(BaseModel):
    content: str


def _summary(file: LibraryFile, user: User) -> dict[str, Any]:
    return {
        "key": file.key,
        "filename": file.filename,
        "title": file.title,
        "description": file.description,
        "can_edit": user.is_admin,
    }


def _detail(file: LibraryFile, user: User) -> dict[str, Any]:
    content = service.read_text(file)
    return {**_summary(file, user), "content": content or "", "exists": content is not None}


@router.get("/library/files")
def list_library_files(user: User = Depends(current_user)) -> list[dict[str, Any]]:
    return [_summary(file, user) for file in service.library_files()]


@router.get("/library/files/{file_key}")
def get_library_file(file_key: str, user: User = Depends(current_user)) -> dict[str, Any]:
    return _detail(service.get_library_file(file_key), user)


@router.put("/library/files/{file_key}")
def save_library_file(file_key: str, body: LibraryFileContent, user: User = Depends(require_admin)) -> dict[str, Any]:
    service.save(file_key, body.content)
    return _detail(service.get_library_file(file_key), user)


@router.get("/ui-texts/intention")
def get_intention_texts(user: User = Depends(current_user)) -> dict[str, Any]:
    """Libellés, placeholders et aides de la section « Objectifs et intention » du constructeur."""
    return service.load("intention")
