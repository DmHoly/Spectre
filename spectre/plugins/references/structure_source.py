"""Les versions de référence comme structures nommées (:mod:`spectre.plugins.structures.sources`) :
une plaque peut porter une version de référence sans étude (plugin wafers)."""

from __future__ import annotations

from typing import Any

from ...kernel.errors import InvalidInput
from ..structures.sources import Resolved, StructureSource, register
from . import service


def _resolve(user: Any, slug: str, version: str | None) -> Resolved:
    number = version or (service.version_numbers(slug) or [None])[-1]
    if not number:
        raise InvalidInput("Cette référence n'a encore aucune version.", code="reference_without_version")
    found = service.get_version(user, slug, number)
    return Resolved(number, f"{found['reference']['name']} {number}", found.get("structure_svg"))


register(StructureSource(kind="reference", plugin="references", resolve=_resolve))
