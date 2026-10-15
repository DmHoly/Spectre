"""La forme des éléments de bibliothèque tels que l'API les rend (:mod:`.api`, et le plugin
promotion pour une brique) : ses champs, sa portée, ses auteurs (id et nom) et si le demandeur
peut le modifier ; une brique, avec ses versions et sa référence."""

from __future__ import annotations

from typing import Any

from ..accounts import service as accounts
from ..accounts.service import User
from . import service
from .service import Entry
from .tech_bricks import brick_changes


class ItemSerializer:
    """Un élément tel que l'API le rend : ses champs, sa portée, ses auteurs (id et nom) et si le
    demandeur peut le modifier. Les noms des comptes sont lus une fois par réponse."""

    def __init__(self, user: User):
        self.user = user
        self._names: dict[int, str | None] = {}

    def account(self, user_id: int | None) -> dict[str, Any] | None:
        if user_id is None:
            return None
        if user_id not in self._names:
            account = accounts.get_by_id(user_id)
            self._names[user_id] = account.name if account else None
        return {"id": user_id, "name": self._names[user_id]}

    def __call__(self, entry: Entry) -> dict[str, Any]:
        return {
            **entry.item.model_dump(mode="json"),
            "scope": entry.scope,
            "microproject": entry.microproject.slug if entry.microproject else None,
            "created_by": self.account(entry.item.created_by),
            "updated_by": self.account(entry.item.updated_by),
            "can_edit": service.can_edit(entry, self.user),
        }


def brick_payload(entry: Entry, user: User, *, detail: bool) -> dict[str, Any]:
    """Une brique telle que l'API la rend : dans une liste, ses versions sans leur contenu ; seule
    (``detail``), chaque version avec son contenu et, en mots, ce qui change depuis la précédente
    (``changes``, :func:`tech_bricks.brick_changes`). Les auteurs des versions et de la promotion
    sont nommés comme ceux de la brique."""
    serializer = ItemSerializer(user)
    payload = serializer(entry)
    versions = entry.item.versions
    payload["versions"] = [
        {
            **version.model_dump(mode="json", exclude=set() if detail else {"content"}),
            "created_by": serializer.account(version.created_by),
            **({"changes": brick_changes(versions[i - 1].content, version.content) if i else []} if detail else {}),
        }
        for i, version in enumerate(versions)
    ]
    if entry.item.reference is not None:
        payload["reference"] = {**entry.item.reference.model_dump(mode="json"), "promoted_by": serializer.account(entry.item.reference.promoted_by)}
    return payload
