"""Les versions de référence dans le comparateur (:mod:`spectre.plugins.comparator`) : le jeton
``reference:<slug>[@<numéro>]`` désigne l'instantané d'une version (la dernière publiée sans
numéro), lu sans son étude ; la saisie d'un nom propose les versions des références qui y répondent,
la plus récente d'abord."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..accounts.service import User
from ..comparator.service import Compared, ItemSource, register_source
from ..structures import kinds
from ..structures.simulation import STEP_IDS_METADATA_KEY
from . import service

PER_REFERENCE = 4  # les versions proposées par référence, la plus récente d'abord


def item_of(slug: str, number: str) -> str:
    return f"reference:{slug}@{number}"


def _resolve(user: User, body: str) -> list[Compared]:
    slug, _sep, number = body.partition("@")
    reference, version = service.read_version(slug.strip(), number.strip() or None)
    state = service.snapshot_state(version.snapshot)
    process = state.metadata.get("structureforge_process")
    return [
        Compared(
            item_of(reference.slug, version.number),
            "reference",
            reference.name,
            version=version.number,
            sublabel=str(version.snapshot.get("title") or ""),
            context="Référence",
            url=f"/references/{quote(reference.slug, safe='')}?version={quote(version.number, safe='')}",
            structure_kind=kinds.structure_kind_name(state.structure_type),
            process=process if isinstance(process, dict) else None,
            step_ids=list(state.metadata.get(STEP_IDS_METADATA_KEY) or state.step_ids),
            metadata=state.metadata,
        )
    ]


def _search(user: User, q: str, limit: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for reference in service.list_references(user, q):
        latest = reference.get("latest_version")
        if not latest:
            continue
        numbers = list(reversed(service.version_numbers(reference["slug"])))[:PER_REFERENCE]
        for number in numbers:
            candidates.append(
                {
                    "item": item_of(reference["slug"], number),
                    "source": "reference",
                    "label": f"{reference['name']} {number}",
                    "sublabel": "Référence" + (" · dernière version" if number == latest["number"] else ""),
                }
            )
        if len(candidates) >= limit:
            break
    return candidates[:limit]


register_source(ItemSource("reference", _resolve, _search, plugin="references", order=30))
