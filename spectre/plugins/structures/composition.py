"""Combiner des études « au marché » : une nouvelle structure faite des briques de plusieurs sources -
la zone active de l'une, l'EBL d'une autre, le p-GaN d'une troisième. Rien n'est stocké ici : le
constructeur envoie les procédés des sources (celui d'une plaque d'une étude, celui d'une version de
référence - lus par leurs propres routes) et, pour chaque brique, la source choisie ; il reçoit le
procédé assemblé, qu'il ouvre comme n'importe quel point de départ.

Les briques s'alignent **par leur nom** (casse et espaces ignorés) : « Zone active » de A et « zone
active » de B sont la même brique. L'ordre des couches est celui de la **source principale** (la
première) ; une brique qu'elle n'a pas se place après celle qui la précède dans sa propre source, et
n'est incluse que si on la choisit. Les étapes de la source principale hors de toute brique restent
où elles sont ; celles des autres sources, hors brique, ne sont pas reprises. Le substrat est une
ligne comme une autre (:data:`SUBSTRATE_ROW`).

Les étapes reprises de la source principale gardent leur id (la nouvelle étude en descend) ; celles
venues d'ailleurs repartent sans id : ce sont de nouvelles étapes pour elle.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ...kernel.errors import InvalidInput

from .schemas import ProcessInput

SUBSTRATE_ROW = "substrat"  # la clé de la ligne du substrat - aucune brique ne la porte (voir brick_key)
MIN_SOURCES = 2
MAX_SOURCES = 4


def brick_key(name: str) -> str:
    """La clé d'alignement d'une brique : son nom sans casse ni espaces superflus (jamais
    :data:`SUBSTRATE_ROW`, réservée au substrat - préfixée au besoin)."""
    key = re.sub(r"\s+", " ", name or "").strip().casefold()
    return f"brique:{key}" if key == SUBSTRATE_ROW else key


@dataclass
class _Source:
    """Une source lue : son procédé validé et, dans l'ordre, ses segments - une brique (``key``, ses
    positions d'étape) ou une étape hors brique (``key`` None)."""

    process: ProcessInput
    steps: list[dict[str, Any]]
    segments: list[tuple[str | None, list[int]]] = field(default_factory=list)
    bricks: dict[str, dict[str, Any]] = field(default_factory=dict)  # clé -> {name, group_id, source, step_indexes}

    @classmethod
    def read(cls, process: ProcessInput) -> "_Source":
        steps = [step.model_dump(mode="json") for step in process.steps]
        source = cls(process=process, steps=steps)
        owner: dict[int, str] = {}
        for brick in process.bricks:
            key = brick_key(brick.name)
            if not key or key in source.bricks:
                continue  # deux briques du même nom dans une source : la première compte
            source.bricks[key] = {"name": brick.name.strip(), "group_id": brick.group_id, "source": brick.source, "step_indexes": list(brick.step_indexes)}
            owner.update({i: key for i in brick.step_indexes})
        index = 0
        while index < len(steps):
            key = owner.get(index)
            if key is None:
                source.segments.append((None, [index]))
                index += 1
            else:
                span = source.bricks[key]["step_indexes"]
                source.segments.append((key, span))
                index = span[-1] + 1
        return source

    def signature(self, key: str) -> str:
        """Ce qui fait l'identité d'une brique (ou du substrat) : ses étapes, leurs paramètres
        déclarés et leurs étiquettes - deux sources de même signature ont la même brique."""
        if key == SUBSTRATE_ROW:
            return json.dumps(self.process.substrate.model_dump(mode="json"), sort_keys=True)
        positions = self.bricks[key]["step_indexes"]
        return json.dumps(
            [
                [
                    self.steps[i],
                    [p.model_dump(mode="json") for p in self.process.declared_params.get(str(i), [])],
                    self.process.layer_labels[str(i)].model_dump(mode="json") if str(i) in self.process.layer_labels else None,
                ]
                for i in positions
            ],
            sort_keys=True,
        )


def _rows(sources: list[_Source]) -> list[str]:
    """Les clés des lignes, dans l'ordre des couches : le substrat, les briques de la source
    principale, et chaque brique qu'elle n'a pas, avant celle qui la suit dans sa propre source
    (tout en haut si rien ne la suit)."""
    order = [SUBSTRATE_ROW] + [key for key, _ in sources[0].segments if key is not None]
    for source in sources[1:]:
        own = [key for key, _ in source.segments if key is not None]
        for at in range(len(own) - 1, -1, -1):
            key = own[at]
            if key in order:
                continue
            following = next((later for later in own[at + 1 :] if later in order), None)
            order.insert(order.index(following) if following else len(order), key)
    return order


def rows_payload(sources: list[_Source], choices: list[int | None]) -> list[dict[str, Any]]:
    """Une ligne par brique (et le substrat) : son nom, les sources qui l'ont (``present``), les
    groupes de sources qui ont exactement la même (``same_as`` : pour chaque source, l'index de la
    première source identique, ``None`` si elle ne l'a pas) et la source choisie (``chosen``)."""
    payload = []
    for key, chosen in zip(_rows(sources), choices):
        present = [key == SUBSTRATE_ROW or key in source.bricks for source in sources]
        signatures = [source.signature(key) if has else None for source, has in zip(sources, present)]
        same_as = [None if sig is None else signatures.index(sig) for sig in signatures]
        name = "Substrat" if key == SUBSTRATE_ROW else next(source.bricks[key]["name"] for source in sources if key in source.bricks)
        payload.append({"key": key, "name": name, "present": present, "same_as": same_as, "chosen": chosen, "in_main": present[0]})
    return payload


def _default_choices(sources: list[_Source]) -> list[int | None]:
    """Par défaut, la source principale pour ce qu'elle a ; rien pour une brique qu'elle n'a pas."""
    return [0 if key == SUBSTRATE_ROW or key in sources[0].bricks else None for key in _rows(sources)]


def _checked_choices(sources: list[_Source], choices: list[int | None] | None) -> list[int | None]:
    keys = _rows(sources)
    if choices is None:
        return _default_choices(sources)
    if len(choices) != len(keys):
        raise InvalidInput(f"Il faut un choix par ligne ({len(keys)}).", code="bad_choices")
    for key, choice in zip(keys, choices):
        if choice is None:
            if key == SUBSTRATE_ROW:
                raise InvalidInput("Le substrat vient forcément d'une des sources.", code="bad_choices")
            continue
        if not 0 <= choice < len(sources) or not (key == SUBSTRATE_ROW or key in sources[choice].bricks):
            raise InvalidInput("Une brique est choisie dans une source qui ne l'a pas.", code="bad_choices")
    return list(choices)


def compose(processes: list[ProcessInput], choices: list[int | None] | None = None) -> dict[str, Any]:
    """Les lignes à choisir (``rows``, :func:`rows_payload`) et le procédé assemblé selon
    ``choices`` (un index de source par ligne, ``None`` : brique non reprise ; ``None`` pour tout :
    les choix par défaut) - au format d'un procédé éditable (``substrate``, ``steps`` avec leur id
    pour celles de la source principale, ``declared_params``, ``layer_labels``, ``bricks``,
    ``recipes``, ``preset_origins``), et ``warnings`` (ce qu'il faut vérifier)."""
    if not MIN_SOURCES <= len(processes) <= MAX_SOURCES:
        raise InvalidInput(f"Choisissez de {MIN_SOURCES} à {MAX_SOURCES} sources à combiner.", code="too_few_sources")
    sources = [_Source.read(process) for process in processes]
    if not sources[0].bricks:
        raise InvalidInput(
            "La source principale n'a pas de brique nommée : groupez ses étapes en briques (zone active, EBL, p-GaN…) "
            "dans le constructeur pour pouvoir la combiner.",
            code="no_bricks",
        )
    if not any(source.bricks for source in sources[1:]):
        raise InvalidInput("Les autres sources n'ont pas de brique nommée : rien à y prendre.", code="no_bricks")
    chosen = _checked_choices(sources, choices)
    keys = _rows(sources)
    pick = dict(zip(keys, chosen))

    # le squelette, dans l'ordre des lignes : chaque brique, précédée pour celles de la source
    # principale des étapes hors brique qui la précèdent chez elle ; les dernières de ces étapes à la fin
    before: dict[str, list[int]] = {}
    loose: list[int] = []
    for key, positions in sources[0].segments:
        if key is None:
            loose.extend(positions)
        else:
            before[key], loose = loose, []
    skeleton: list[tuple[str | None, list[int]]] = []
    for key in keys[1:]:
        if before.get(key):
            skeleton.append((None, before[key]))
        skeleton.append((key, []))
    if loose:
        skeleton.append((None, loose))

    steps: list[dict[str, Any]] = []
    declared: dict[str, Any] = {}
    labels: dict[str, Any] = {}
    presets: dict[str, Any] = {}
    bricks: list[dict[str, Any]] = []
    used: list[int] = []
    group_ids: set[str] = set()

    def take(source_index: int, position: int) -> None:
        source = sources[source_index]
        step = dict(source.steps[position])
        own_id = source.process.step_ids[position] if source_index == 0 else None
        if own_id:
            step = {"id": own_id, **step}
        at = str(len(steps))
        steps.append(step)
        if str(position) in source.process.declared_params:
            declared[at] = [p.model_dump(mode="json") for p in source.process.declared_params[str(position)]]
        if str(position) in source.process.layer_labels:
            labels[at] = source.process.layer_labels[str(position)].model_dump(mode="json")
        if str(position) in source.process.preset_origins:
            presets[at] = source.process.preset_origins[str(position)].model_dump(mode="json")

    for key, positions in skeleton:
        if key is None:
            for position in positions:
                take(0, position)
            continue
        source_index = pick.get(key)
        if source_index is None:
            continue
        brick = sources[source_index].bricks[key]
        start = len(steps)
        for position in brick["step_indexes"]:
            take(source_index, position)
        group_id = brick["group_id"]
        if group_id in group_ids:
            group_id = f"{group_id}-{len(bricks) + 1}"
        group_ids.add(group_id)
        bricks.append({"group_id": group_id, "name": brick["name"], "source": brick["source"], "step_indexes": list(range(start, len(steps)))})
        used.append(source_index)

    substrate_from = pick[SUBSTRATE_ROW]
    recipes, warnings = _merged_recipes(sources, [0, substrate_from, *used])
    return {
        "rows": rows_payload(sources, chosen),
        "process": {
            "substrate": sources[substrate_from].process.substrate.model_dump(mode="json"),
            "steps": steps,
            "declared_params": declared,
            "layer_labels": labels,
            "bricks": bricks,
            "recipes": recipes,
            "preset_origins": presets,
        },
        "warnings": warnings,
    }


def _merged_recipes(sources: list[_Source], used: list[int]) -> tuple[dict[str, Any], list[str]]:
    """Les recettes propres des sources utilisées, réunies par nom (la source principale d'abord) ;
    deux recettes du même nom mais différentes : la première gardée, signalée."""
    merged: dict[str, dict[str, dict[str, Any]]] = {"deposition": {}, "etch": {}}
    warnings = []
    for index in dict.fromkeys(used):
        recipes = sources[index].process.recipes
        for kind in ("deposition", "etch"):
            for recipe in getattr(recipes, kind):
                dumped = recipe.model_dump(mode="json")
                name = recipe.name.strip()
                if name not in merged[kind]:
                    merged[kind][name] = dumped
                elif merged[kind][name] != dumped:
                    warnings.append(f"Deux recettes « {name} » différentes : celle de la première source est gardée - vérifiez les étapes qui l'utilisent.")
    return {kind: list(by_name.values()) for kind, by_name in merged.items()}, warnings
