"""Les structures de la bibliothèque comme structures nommées
(:mod:`spectre.plugins.structures.sources`) : simulées par StructureForge puis dessinées, pour
qu'une plaque en porte une sans étude (plugin wafers)."""

from __future__ import annotations

from typing import Any

from ...kernel.errors import DomainError, InvalidInput
from ..structures import kinds
from ..structures.sources import Resolved, StructureSource, register
from . import service


def _resolve(user: Any, item_id: str, version: str | None) -> Resolved:
    item = service.get_item(service.SAVED_STRUCTURES, user, item_id).item
    try:
        structure, _origins = kinds.simulate_recorded_process(item.model_dump())
        svg = kinds.render_process_svg(structure)
    except DomainError:
        raise
    except Exception as exc:  # noqa: BLE001 - une simulation qui ne passe pas se dit, sans 500
        raise InvalidInput(f"La structure « {item.name} » ne se simule pas : {exc}", code="saved_structure_not_simulated") from exc
    return Resolved(None, item.name, svg)


register(StructureSource(kind="saved", plugin="process_library", resolve=_resolve))
