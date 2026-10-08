"""Combiner des études « au marché » : une nouvelle structure faite des étapes de plusieurs sources -
la zone active de l'une, l'EBL d'une autre, un recuit ajouté, une gravure humide à la place d'une
gravure sèche. Rien n'est stocké ici : le constructeur envoie les procédés des sources (celui d'une
plaque d'une étude, celui d'une version de référence - lus par leurs propres routes) et, pour chaque
étape, la source choisie ; il reçoit le procédé assemblé, qu'il ouvre comme n'importe quel départ.

**Une ligne par étape.** Deux étapes de deux sources sont la même ligne quand elles ont le même
identifiant d'étape (elles descendent de la même étape, d'une même référence), sinon quand elles
ont le même type et le même nom dans une brique du même nom (casse et espaces ignorés) - la n-ième
avec la n-ième. Une étape qu'une seule source a est une ligne « ajoutée ».

**L'ordre** est celui de la **source principale** (la première) ; une étape qu'elle n'a pas se place
avant celle qui la suit dans sa propre source (tout en haut si rien ne la suit), et n'est reprise
que si on la choisit. Le substrat est une ligne comme une autre (:data:`SUBSTRATE_ROW`).

**Remplacer** : une ligne choisie peut en remplacer une autre (``replaces``) - elle prend sa place
dans l'ordre et sa brique, et l'autre n'est pas reprise.

**Les briques** ne servent plus qu'à regrouper : une source sans brique se combine aussi. Dans le
procédé assemblé, les étapes consécutives d'une même brique (celle de leur source, celle de l'étape
remplacée pour une étape qui en remplace une) forment une brique.

Une étape que la principale a aussi (la même ligne) garde l'id qu'elle a chez elle, d'où que viennent
ses valeurs : la nouvelle étude en descend, et s'y compare étape par étape. Une étape ajoutée ou qui
en remplace une autre repart sans id : c'est une nouvelle étape pour elle.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ...kernel.errors import InvalidInput

from .schemas import ProcessInput

SUBSTRATE_ROW = "substrat"  # la clé de la ligne du substrat
MIN_SOURCES = 2
MAX_SOURCES = 4
# les champs dont la valeur résume une étape dans le tableau (le premier présent)
_SUMMARY_FIELDS = ("thickness", "depth", "height", "temperature", "duration", "time")


def name_key(name: str | None) -> str:
    """Un nom sans casse ni espaces superflus - pour aligner briques et étapes."""
    return re.sub(r"\s+", " ", name or "").strip().casefold()


@dataclass
class _Source:
    """Une source lue : son procédé validé, ses étapes (sans id), l'id de chacune, la brique de
    chacune (``None`` hors brique) et, par clé de brique, ce qu'on garde d'elle."""

    process: ProcessInput
    steps: list[dict[str, Any]]
    ids: list[str | None]
    brick_of: list[str | None]  # la clé de la brique de chaque étape
    bricks: dict[str, dict[str, Any]] = field(default_factory=dict)  # clé -> {name, group_id, source}

    @classmethod
    def read(cls, process: ProcessInput) -> "_Source":
        steps = [step.model_dump(mode="json") for step in process.steps]
        brick_of: list[str | None] = [None] * len(steps)
        bricks: dict[str, dict[str, Any]] = {}
        for brick in process.bricks:
            key = name_key(brick.name)
            if not key:
                continue
            bricks.setdefault(key, {"name": brick.name.strip(), "group_id": brick.group_id, "source": brick.source})
            for i in brick.step_indexes:
                if 0 <= i < len(steps) and brick_of[i] is None:
                    brick_of[i] = key
        return cls(process=process, steps=steps, ids=list(process.step_ids), brick_of=brick_of, bricks=bricks)

    def signature(self, position: int | None) -> str:
        """Ce qui fait l'identité d'une étape (ou du substrat, ``None``) : ses champs, ses paramètres
        déclarés et son étiquette - deux sources de même signature ont la même étape."""
        if position is None:
            return json.dumps(self.process.substrate.model_dump(mode="json"), sort_keys=True)
        label = self.process.layer_labels.get(str(position))
        return json.dumps(
            [
                self.steps[position],
                [p.model_dump(mode="json") for p in self.process.declared_params.get(str(position), [])],
                label.model_dump(mode="json") if label is not None else None,
            ],
            sort_keys=True,
        )

    def summary(self, position: int | None) -> str:
        """La valeur qui résume une étape (« 20 nm », « 700 °C »), vide sans elle."""
        if position is None:
            substrate = self.process.substrate
            return f"{substrate.material}"
        step = self.steps[position]
        for name in _SUMMARY_FIELDS:
            value = step.get(name)
            if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
                return f"{value['value']:g} {value.get('unit') or ''}".strip()
        return ""

    def brick_name(self, position: int) -> str | None:
        key = self.brick_of[position]
        return self.bricks[key]["name"] if key else None


def _line_keys(sources: list[_Source]) -> list[list[str]]:
    """La clé de ligne de chaque étape de chaque source : ``id:<id>`` pour un id que plusieurs
    sources ont, sinon ``nom:<brique>|<type>|<nom>#<n>`` (la n-ième de ce nom chez elle) - une clé
    qu'une seule source porte est une étape ajoutée."""
    holders: dict[str, set[int]] = {}
    for s, source in enumerate(sources):
        for step_id in source.ids:
            if step_id:
                holders.setdefault(step_id, set()).add(s)
    keys = []
    for s, source in enumerate(sources):
        seen: dict[str, int] = {}
        own = []
        for i, step in enumerate(source.steps):
            step_id = source.ids[i]
            if step_id and len(holders.get(step_id, ())) > 1 and f"id:{step_id}" not in own:
                own.append(f"id:{step_id}")
                continue
            base = f"nom:{source.brick_of[i] or ''}|{step.get('kind')}|{name_key(step.get('name'))}"
            seen[base] = seen.get(base, 0) + 1
            own.append(f"{base}#{seen[base]}")
        keys.append(own)
    return keys


def _order(keys: list[list[str]]) -> list[str]:
    """Les clés des lignes dans l'ordre des couches : le substrat, les étapes de la principale, et
    chaque étape qu'elle n'a pas, avant celle qui la suit dans sa propre source (en haut sinon)."""
    order = [SUBSTRATE_ROW, *keys[0]]
    for own in keys[1:]:
        for at in range(len(own) - 1, -1, -1):
            if own[at] in order:
                continue
            following = next((later for later in own[at + 1 :] if later in order), None)
            order.insert(order.index(following) if following else len(order), own[at])
    return order


@dataclass
class _Line:
    key: str
    positions: list[int | None]  # la position de l'étape dans chaque source (None : elle ne l'a pas)


def _lines(sources: list[_Source]) -> list[_Line]:
    keys = _line_keys(sources)
    where = [{key: i for i, key in enumerate(own)} for own in keys]
    lines = [_Line(SUBSTRATE_ROW, [None] * len(sources))]
    for key in _order(keys)[1:]:
        lines.append(_Line(key, [w.get(key) for w in where]))
    return lines


def _present(line: _Line, s: int) -> bool:
    return line.key == SUBSTRATE_ROW or line.positions[s] is not None


def _rows_payload(sources: list[_Source], lines: list[_Line], choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une ligne par étape (et le substrat) : son nom, son type, sa brique, les sources qui l'ont
    (``present``), pour chacune la première source identique (``same_as``) et sa valeur (``summary``),
    la source choisie (``chosen``), la ligne qu'elle remplace (``replaces``) et ``in_main``."""
    payload = []
    for line, choice in zip(lines, choices):
        present = [_present(line, s) for s in range(len(sources))]
        signatures = [source.signature(line.positions[s]) if present[s] else None for s, source in enumerate(sources)]
        holder = next(s for s in range(len(sources)) if present[s])
        if line.key == SUBSTRATE_ROW:
            name, kind, brick = "Substrat", "substrate", None
        else:
            step = sources[holder].steps[line.positions[holder]]
            name, kind = step.get("name") or step.get("kind"), step.get("kind")
            brick = sources[holder].brick_name(line.positions[holder])
        payload.append(
            {
                "key": line.key,
                "name": name,
                "kind": kind,
                "brick": brick,
                "present": present,
                "same_as": [None if sig is None else signatures.index(sig) for sig in signatures],
                "summary": [source.summary(line.positions[s]) if present[s] else None for s, source in enumerate(sources)],
                "chosen": choice["source"],
                "replaces": choice["replaces"],
                "in_main": present[0],
            }
        )
    return payload


def _checked_choices(sources: list[_Source], lines: list[_Line], choices: list[Any] | None) -> list[dict[str, Any]]:
    """Un choix par ligne, ``{source, replaces}`` (un index ou ``None`` seul vaut ``{source}``) -
    par défaut, la principale pour ce qu'elle a, rien pour le reste. Refus (``bad_choices``) : une
    source qui n'a pas l'étape, le substrat omis, un remplacement vers une ligne inconnue, vers elle-
    même, d'une ligne non reprise, ou deux fois la même ligne remplacée."""
    if choices is None:
        return [{"source": 0 if _present(line, 0) else None, "replaces": None} for line in lines]
    if len(choices) != len(lines):
        raise InvalidInput(f"Il faut un choix par ligne ({len(lines)}).", code="bad_choices")
    keys = {line.key for line in lines}
    checked, replaced = [], set()
    for line, raw in zip(lines, choices):
        choice = raw if isinstance(raw, dict) else {"source": raw}
        source, target = choice.get("source"), choice.get("replaces")
        if source is None:
            if line.key == SUBSTRATE_ROW:
                raise InvalidInput("Le substrat vient forcément d'une des sources.", code="bad_choices")
            if target is not None:
                raise InvalidInput("Une étape non reprise ne remplace rien.", code="bad_choices")
        elif not isinstance(source, int) or not 0 <= source < len(sources) or not _present(line, source):
            raise InvalidInput("Une étape est choisie dans une source qui ne l'a pas.", code="bad_choices")
        if target is not None:
            if target not in keys or target in (line.key, SUBSTRATE_ROW) or target in replaced or line.key == SUBSTRATE_ROW:
                raise InvalidInput("Ce remplacement n'est pas possible.", code="bad_choices")
            replaced.add(target)
        checked.append({"source": source, "replaces": target})
    replacing = {c["replaces"] for c in checked if c["replaces"]}
    for line, choice in zip(lines, checked):
        if line.key in replacing and choice["replaces"] is not None:
            raise InvalidInput("Une étape remplacée ne remplace pas une autre étape.", code="bad_choices")
    return checked


def compose(processes: list[ProcessInput], choices: list[Any] | None = None) -> dict[str, Any]:
    """Les lignes à choisir (``rows``, une par étape) et le procédé assemblé selon ``choices`` (un
    choix par ligne : ``{source, replaces}``, ou l'index de la source, ``None`` : pas reprise ;
    ``None`` pour tout : les choix par défaut) - au format d'un procédé éditable (``substrate``,
    ``steps`` avec leur id pour celles de la source principale, ``declared_params``,
    ``layer_labels``, ``bricks``, ``recipes``, ``preset_origins``), et ``warnings``."""
    if not MIN_SOURCES <= len(processes) <= MAX_SOURCES:
        raise InvalidInput(f"Choisissez de {MIN_SOURCES} à {MAX_SOURCES} sources à combiner.", code="too_few_sources")
    sources = [_Source.read(process) for process in processes]
    if not any(source.steps for source in sources):
        raise InvalidInput("Aucune des sources n'a d'étape à reprendre.", code="no_steps")
    lines = _lines(sources)
    chosen = _checked_choices(sources, lines, choices)
    by_key = {line.key: (line, choice) for line, choice in zip(lines, chosen)}
    replaced_by = {choice["replaces"]: line.key for line, choice in zip(lines, chosen) if choice["replaces"]}

    steps: list[dict[str, Any]] = []
    declared: dict[str, Any] = {}
    labels: dict[str, Any] = {}
    presets: dict[str, Any] = {}
    brick_runs: list[tuple[str | None, int]] = []  # (clé de brique, source qui la porte) par étape
    used: list[int] = []

    def take(s: int, position: int, brick_key: str | None, brick_source: int, own_id: str | None) -> None:
        source = sources[s]
        step = dict(source.steps[position])
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
        brick_runs.append((brick_key, brick_source))
        used.append(s)

    for line in lines[1:]:
        _, choice = by_key[line.key]
        if choice["replaces"] is not None:
            continue  # elle se place où était l'étape qu'elle remplace
        if line.key in replaced_by:
            # l'étape qui la remplace, à sa place et dans sa brique
            other, other_choice = by_key[replaced_by[line.key]]
            s = other_choice["source"]
            holder = next(h for h in range(len(sources)) if _present(line, h))
            # une étape de la principale déplacée garde son id ; venue d'ailleurs, c'est une nouvelle étape
            own_id = sources[0].ids[other.positions[0]] if s == 0 else None
            take(s, other.positions[s], sources[holder].brick_of[line.positions[holder]], holder, own_id)
            continue
        s = choice["source"]
        if s is None:
            continue
        # la même ligne chez la principale : l'étape garde son id (prise ailleurs, ce sont d'autres valeurs)
        main_id = sources[0].ids[line.positions[0]] if line.positions[0] is not None else None
        take(s, line.positions[s], sources[s].brick_of[line.positions[s]], s, main_id)

    # les briques : les étapes consécutives d'une même brique
    bricks: list[dict[str, Any]] = []
    group_ids: set[str] = set()
    start = 0
    while start < len(brick_runs):
        key, s = brick_runs[start]
        end = start + 1
        while end < len(brick_runs) and key is not None and brick_runs[end][0] == key:
            end += 1
        if key is not None:
            brick = sources[s].bricks[key]
            group_id = brick["group_id"]
            if group_id in group_ids:
                group_id = f"{group_id}-{len(bricks) + 1}"
            group_ids.add(group_id)
            bricks.append({"group_id": group_id, "name": brick["name"], "source": brick["source"], "step_indexes": list(range(start, end))})
        start = end

    substrate_from = by_key[SUBSTRATE_ROW][1]["source"]
    recipes, warnings = _merged_recipes(sources, [0, substrate_from, *used])
    return {
        "rows": _rows_payload(sources, lines, chosen),
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
