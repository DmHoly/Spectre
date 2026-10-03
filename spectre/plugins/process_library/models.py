"""Ce que portent tous les éléments d'une bibliothèque (structure enregistrée, préset d'étape,
brique) : un identifiant opaque, un nom - qui n'est qu'un champ - et leur traçabilité. Leur portée
(intégré, partagé, µprojet) se lit à l'endroit où ils sont rangés, pas dans l'élément."""

from __future__ import annotations

from pydantic import BaseModel


class LibraryItem(BaseModel):
    id: str = ""  # attribué à la création ; celui d'un élément intégré dérive de son nom
    name: str
    created_by: int | None = None  # id du compte ; None pour un élément intégré ou antérieur à cette trace
    updated_by: int | None = None
    created_at: str
