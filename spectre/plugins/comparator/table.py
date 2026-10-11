"""Le tableau d'une comparaison de structures (:func:`build`) : une ligne par plaque ou par
structure, une colonne par paramètre - regroupées par étape, le substrat d'abord -, chaque cellule
comparée à la ligne de base. Pur : ni dépôt ni HTTP, ce qu'on compare arrive déjà lu
(:class:`Compared`, voir :mod:`.service`).

Le code couleur (décidé le 2026-10-11), le statut de chaque cellule :

- ``changed`` (rouge) : la valeur n'est pas celle de la base (un paramètre retiré compris) ;
- ``added_param`` (violet) : une colonne que l'étape de la base n'a pas - un paramètre ajouté, un
  paramètre déclaré qu'on a compris depuis ;
- ``added_layer`` (vert) : une étape - une couche - que la base n'a pas ;
- ``moved`` (orange) : l'étape n'est pas à la même place dans l'ordre du procédé (``changed`` dit
  en plus si sa valeur a changé) ;
- ``absent`` : la base a cette étape, pas cette structure (une couche retirée) ;
- ``same`` : comme la base ; ``empty`` : ni la base ni cette structure n'ont l'étape ; ``na`` :
  une ligne sans ce genre de colonnes (un split déclaré face à un procédé).

**Appariement des étapes.** Deux structures qui partagent des ids d'étape (deux versions d'une
piste, les variantes d'une campagne, une étude et sa fourche, une version de référence et l'étude
publiée) s'apparient par id ; les autres étapes par type et matériau, dans l'ordre : la plus
longue sous-suite commune pondérée (même id ≫ même type et même matériau > même type). Une étape
appariée par id hors de cet ordre, ou restée seule avec sa jumelle (même type, même matériau), est
déplacée ; une étape restée seule s'ajoute après la dernière étape appariée qui la précède.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from structureforge.core.units import Length

from ..structures import kinds
from ..structures.campaigns import CAMPAIGN_FIELD_LABELS
from ..structures.rendering import format_number, length_text, value_text
from ..structures.simulation import LATTICE_OPENING_KEY, LATTICE_OPENING_SIZES, split_declared_unit

CHANGED = "changed"
ADDED_PARAM = "added_param"
ADDED_LAYER = "added_layer"
MOVED = "moved"
ABSENT = "absent"
SAME = "same"
EMPTY = "empty"
NOT_APPLICABLE = "na"

# ce qui compte comme une différence avec la base (une colonne, une étape, une ligne)
_DIFFERENCES = {CHANGED, ADDED_PARAM, ADDED_LAYER, MOVED, ABSENT}

STEP_KIND_LABELS = {
    "deposition": "Dépôt",
    "etch": "Gravure",
    "planarization": "Planarisation",
    "lithography": "Lithographie",
    "chemical": "Étape chimique",
    "resist_strip": "Retrait de résine",
    "faceted_growth": "Croissance facettée",
    "facet_envelope": "Rattrapage des plans",
    "epitaxial_growth": "Croissance épitaxiale",
    "flip": "Retournement",
}

_FIELD_LABELS = {
    **CAMPAIGN_FIELD_LABELS,
    "seed_materials": "Matériaux d'amorçage",
    "c_plane": "Plan C",
    "m_plane": "Plan M",
    "openings": "Ouvertures",
    "lattice_anchor": "Ancrage au réseau",
    "substrate.pitch": "Pas du réseau",
}
_UNITS = {"semi_polar_angle_deg": "°", "angle_deg": "°", "rate_c": "× réf.", "rate_m": "× réf.", "rate_sp": "× réf.", "rate_sp_inv": "× réf."}
_ORIENTATIONS = {"c_plane": "Plan C", "m_plane": "Plan M", "semi_polar": "Semi-polaire"}
_ANCHOR_MODES = {"wires": "un trou par fil", "between": "entre les fils", "pixel": "pixel entier"}
_RECIPE_KINDS = {"deposition": "deposition", "etch": "etch"}
# des champs qu'une colonne ne montre pas : l'identité de l'étape, son nom (l'en-tête), et ce
# qu'une colonne dédiée dit autrement (ouvertures, ancrage, paramètres d'une étape chimique)
_NOT_COLUMNS = {"id", "kind", "name", "description", "openings", LATTICE_OPENING_KEY, "parameters"}
PRESENT_COLUMN = "present"  # la seule colonne d'une étape sans paramètre (un retournement)

SUBSTRATE_KEY = "substrate"
DECLARED_KEY = "declared"


@dataclass
class Compared:
    """Une ligne du tableau, telle qu'une source la lit (:mod:`.service`) : ``item``, le jeton qui la
    désigne exactement (une variante de campagne a le sien) ; ``source`` (``study``, ``wafer``,
    ``reference``) ; ce qui la nomme (``label``, ``version``, ``sublabel``, ``context``) ; son procédé (``process`` : ``structureforge_process``, les
    valeurs d'une variante appliquées) et les ids de ses étapes ; les métadonnées de sa version (les
    retouches : noms d'étape, étiquettes) ; le split déclaré d'une étude sans structure
    (``declared`` : ``(facteurs, valeurs)``) ; ``note`` quand il n'y a rien à comparer (des
    images), ``error`` quand elle n'a pu être lue."""

    item: str
    source: str
    label: str
    version: str | None = None  # « v1.2 », « 1.1 » : la version de la structure
    sublabel: str = ""
    context: str = ""  # le µprojet, « Référence »...
    url: str | None = None
    structure_kind: str = "process"
    process: dict[str, Any] | None = None
    step_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] | None = None
    declared: tuple[list[str], list[str]] | None = None
    wafers: list[str] = field(default_factory=list)
    badge: str | None = None
    note: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class _Value:
    key: Any  # ce qu'on compare
    text: str
    title: str = ""


@dataclass(eq=False)
class _Step:
    id: str | None
    kind: str
    name: str
    identity: tuple[str, str]  # (type, matériau ou recette) : la jumelle d'une étape sans id commun
    values: dict[str, _Value]
    labels: dict[str, str]
    position: int


@dataclass(eq=False)
class _Slot:
    """Une étape du tableau (un groupe de colonnes) : celle de la base, ou ajoutée par une ligne."""

    first: _Step
    in_baseline: bool
    ids: set[str] = field(default_factory=set)


# -- valeurs -------------------------------------------------------------------------------------


def _number(value: float) -> float:
    return round(float(value), 9)


def _length(raw: Any) -> float | None:
    if not isinstance(raw, dict) or "value" not in raw:
        return None
    try:
        return Length.model_validate(raw).to_nm()
    except (ValueError, TypeError):
        return None


def _value(name: str, raw: Any) -> _Value | None:
    """Une valeur de paramètre, comparable et lisible - ``None`` sans valeur."""
    if raw is None:
        return None
    nm = _length(raw)
    if nm is not None:
        return _Value(("length", _number(nm)), length_text(nm))
    if isinstance(raw, bool):
        return _Value(("bool", raw), "oui" if raw else "non")
    if isinstance(raw, (int, float)) and math.isfinite(raw):
        unit = _UNITS.get(name)
        return _Value(("number", _number(raw)), f"{format_number(float(raw))}{' ' + unit if unit else ''}")
    if isinstance(raw, str):
        if name == "orientation":
            return _Value(("text", raw), _ORIENTATIONS.get(raw, raw))
        return _Value(("text", raw), raw) if raw.strip() else None
    if isinstance(raw, list):
        if not raw:
            return None
        return _Value(("list", json.dumps(raw, sort_keys=True)), ", ".join(str(item) for item in raw))
    return _Value(("json", json.dumps(raw, sort_keys=True, default=str)), json.dumps(raw, ensure_ascii=False, default=str))


def _openings(raw: Any) -> _Value | None:
    """Les ouvertures d'une lithographie dessinée à la main : leur nombre (et leur largeur quand
    elles l'ont toutes), la liste au survol."""
    pairs = [pair for pair in raw or [] if isinstance(pair, (list, tuple)) and len(pair) == 2]
    if not pairs:
        return None
    try:
        spans = [(float(a), float(b)) for a, b in pairs]
    except (TypeError, ValueError):
        return None
    widths = {_number(b - a) for a, b in spans}
    text = f"{len(spans)} × {length_text(next(iter(widths)))}" if len(widths) == 1 else f"{len(spans)} ouvertures"
    title = ", ".join(f"{format_number(a)}–{format_number(b)}" for a, b in spans) + " nm"
    return _Value(("openings", tuple((_number(a), _number(b)) for a, b in spans)), text, title)


def _recipe(step: dict[str, Any], recipes: dict[str, Any]) -> _Value | None:
    """La recette d'une étape : son nom, et sa définition quand le procédé a la sienne sous ce nom
    (deux procédés qui définissent différemment « Gravure HCl » n'ont pas la même recette)."""
    name = step.get("recipe")
    if not isinstance(name, str) or not name.strip():
        return None
    own_kind = _RECIPE_KINDS.get(str(step.get("kind")))
    own = next(
        (recipe for recipe in recipes.get(own_kind) or [] if isinstance(recipe, dict) and str(recipe.get("name", "")).strip() == name.strip()),
        None,
    ) if own_kind else None
    if own is None:
        return _Value(("recipe", name, None), name)
    return _Value(("recipe", name, json.dumps(own, sort_keys=True)), name, "Recette définie dans le procédé")


def _declared(params: Any) -> tuple[dict[str, _Value], dict[str, str]]:
    values: dict[str, _Value] = {}
    labels: dict[str, str] = {}
    for param in params if isinstance(params, list) else []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        name = str(param["name"])
        rest, unit = split_declared_unit(param)
        value = rest.get("value")
        if value in (None, ""):
            continue
        key = f"declared:{name}"
        shown = f"{value_text(value)}{' ' + unit if unit else ''}"
        values[key] = _Value(("declared", json.dumps(value, sort_keys=True, default=str), unit), shown, "Paramètre déclaré")
        labels[key] = name
    return values, labels


def _step(raw: dict[str, Any], position: int, step_id: str | None, declared: Any, recipes: dict[str, Any]) -> _Step:
    kind = str(raw.get("kind") or "")
    values: dict[str, _Value] = {}
    labels: dict[str, str] = {}
    for name, raw_value in raw.items():
        if name in _NOT_COLUMNS:
            continue
        value = _recipe(raw, recipes) if name == "recipe" else _value(name, raw_value)
        labels[name] = _FIELD_LABELS.get(name, name)
        if value is not None:
            values[name] = value
    anchor = raw.get(LATTICE_OPENING_KEY)
    if kind == "lithography" and isinstance(anchor, dict):
        # ancrée au réseau : le mode et sa taille, pas les ouvertures (elles suivent le nombre de fils vus)
        mode = str(anchor.get("mode") or "wires")
        labels["lattice_anchor"] = _FIELD_LABELS["lattice_anchor"]
        values["lattice_anchor"] = _Value(("text", mode), _ANCHOR_MODES.get(mode, mode))
        size = LATTICE_OPENING_SIZES.get(mode)
        if size and isinstance(anchor.get(size), (int, float)):
            key = f"openings.{size}"
            labels[key] = _FIELD_LABELS.get(key, size)
            values[key] = _Value(("length", _number(anchor[size])), length_text(float(anchor[size])))
    elif kind == "lithography":
        labels["openings"] = _FIELD_LABELS["openings"]
        openings = _openings(raw.get("openings"))
        if openings is not None:
            values["openings"] = openings
    parameters = raw.get("parameters")
    for name, raw_value in (parameters.items() if isinstance(parameters, dict) else []):
        key = f"parameters.{name}"
        labels[key] = str(name)
        value = _value(str(name), raw_value)
        if value is not None:
            values[key] = value
    declared_values, declared_labels = _declared(declared)
    values.update(declared_values)
    labels.update(declared_labels)
    material = raw.get("material") or raw.get("resist_material") or raw.get("recipe") or ""
    name = str(raw.get("name") or STEP_KIND_LABELS.get(kind, kind) or f"Étape {position + 1}")
    return _Step(step_id, kind, name, (kind, str(material)), values, labels, position)


def _substrate(raw: Any) -> tuple[dict[str, _Value], dict[str, str]]:
    """Le substrat : son matériau, son épaisseur, et la largeur du domaine - ou, pour un gabarit SAG
    (réseau de fils), le pas du réseau : le nombre de fils vus et la largeur qui en découle ne sont
    qu'une vue (``simulation.view_neutral_process``)."""
    substrate = raw if isinstance(raw, dict) else {}
    lattice = substrate.get("lattice") if isinstance(substrate.get("lattice"), dict) else None
    values: dict[str, _Value] = {}
    labels: dict[str, str] = {}
    for name in ("material", "thickness", *(() if lattice else ("domain_width",))):
        labels[name] = _FIELD_LABELS.get(name, name)
        value = _value(name, substrate.get(name))
        if value is not None:
            values[name] = value
    if lattice:
        labels["substrate.pitch"] = _FIELD_LABELS["substrate.pitch"]
        pitch = lattice.get("pitch")
        if isinstance(pitch, (int, float)):
            values["substrate.pitch"] = _Value(("length", _number(pitch)), length_text(float(pitch)))
    return values, labels


def _steps_of(compared: Compared) -> list[_Step]:
    process = compared.process or {}
    declared = process.get("declared_params") if isinstance(process.get("declared_params"), dict) else {}
    recipes = process.get("recipes") if isinstance(process.get("recipes"), dict) else {}
    raw_steps = [step for step in process.get("steps") or [] if isinstance(step, dict)]
    ids = compared.step_ids if len(compared.step_ids) == len(raw_steps) else [None] * len(raw_steps)
    return [_step(raw, i, ids[i], declared.get(str(i)), recipes) for i, raw in enumerate(raw_steps)]


# -- appariement -----------------------------------------------------------------------------------


def _score(step: _Step, slot: _Slot, forced: _Slot | None, claimed: set[int]) -> int:
    if forced is not None:
        return 1000 if forced is slot else 0
    if id(slot) in claimed or step.kind != slot.first.kind:
        return 0
    if step.identity == slot.first.identity:
        return 20 if step.values == slot.first.values else 10
    return 1


def _align(steps: list[_Step], slots: list[_Slot]) -> tuple[dict[int, _Slot], set[int]]:
    """L'étape du tableau de chaque étape de ``steps`` (par position), et celles qui y sont
    appariées hors de l'ordre (déplacées)."""
    owner = {sid: slot for slot in slots for sid in slot.ids}
    forced = [owner.get(step.id) if step.id else None for step in steps]
    claimed = {id(slot) for slot in forced if slot is not None}
    n, m = len(steps), len(slots)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for j in range(n - 1, -1, -1):
        for k in range(m - 1, -1, -1):
            score = _score(steps[j], slots[k], forced[j], claimed)
            best[j][k] = max(best[j + 1][k], best[j][k + 1], best[j + 1][k + 1] + score if score else 0)
    matched: dict[int, _Slot] = {}
    j = k = 0
    while j < n and k < m:
        score = _score(steps[j], slots[k], forced[j], claimed)
        if score and best[j][k] == best[j + 1][k + 1] + score:
            matched[j] = slots[k]
            j, k = j + 1, k + 1
        elif best[j][k] == best[j + 1][k]:
            j += 1
        else:
            k += 1
    used = {id(slot) for slot in matched.values()}
    moved: set[int] = set()
    for j, slot in enumerate(forced):
        if slot is not None and j not in matched and id(slot) not in used:
            matched[j] = slot
            moved.add(j)
            used.add(id(slot))
    for j, step in enumerate(steps):
        if j in matched or forced[j] is not None:
            continue
        twin = next(
            (slot for slot in slots if id(slot) not in used and id(slot) not in claimed and slot.first.kind == step.kind and slot.first.identity == step.identity),
            None,
        )
        if twin is not None:
            matched[j] = twin
            moved.add(j)
            used.add(id(twin))
    return matched, moved


def _place(steps: list[_Step], slots: list[_Slot], *, baseline: bool) -> dict[int, tuple[_Step, bool]]:
    """Range ``steps`` (une ligne) dans ``slots`` - ses étapes sans pareille y sont ajoutées, après
    la dernière étape appariée qui les précède - et rend ``{id(étape du tableau): (étape, déplacée)}``."""
    matched, moved = _align(steps, slots) if not baseline else ({}, set())
    placed: dict[int, tuple[_Step, bool]] = {}
    anchor: _Slot | None = None
    for j, step in enumerate(steps):
        slot = matched.get(j)
        if slot is None:
            slot = _Slot(step, in_baseline=baseline)
            if baseline:
                slots.append(slot)
            else:
                slots.insert(slots.index(anchor) + 1 if anchor is not None else 0, slot)
            anchor = slot
        elif j not in moved:
            anchor = slot
        if step.id:
            slot.ids.add(step.id)
        placed[id(slot)] = (step, j in moved)
    return placed


# -- cellules --------------------------------------------------------------------------------------


def _cell(value: _Value | None, base: _Value | None, *, status: str, moved_title: str = "") -> dict[str, Any]:
    """La cellule d'une ligne qui a l'étape (``status`` : ce que dit l'étape elle-même - ``same``,
    ``added_layer``, ``moved`` - avant la comparaison de la valeur à celle de la base)."""
    text = value.text if value is not None else "—"
    title = value.title if value is not None else ""
    differs = (value.key if value else None) != (base.key if base else None)
    if status == ADDED_LAYER:
        return {"text": text, "status": ADDED_LAYER, "title": title or "Étape absente de la base"}
    if status == MOVED:
        base_text = f"base : {base.text}" if base is not None and differs else ""
        return {"text": text, "status": MOVED, "changed": differs, "title": "; ".join(t for t in (moved_title, title, base_text) if t)}
    if not differs:
        return {"text": text, "status": SAME, "title": title}
    if base is None:
        return {"text": text, "status": ADDED_PARAM, "title": title or "Paramètre absent de la base"}
    if value is None:
        return {"text": text, "status": CHANGED, "title": f"Paramètre retiré (base : {base.text})"}
    return {"text": text, "status": CHANGED, "title": "; ".join(t for t in (title, f"base : {base.text}") if t)}


def _blank(status: str, title: str = "") -> dict[str, Any]:
    return {"text": "" if status == NOT_APPLICABLE else "—", "status": status, "title": title}


@dataclass
class _Group:
    key: str
    label: str
    kind: str
    kind_label: str
    position: int | None
    columns: list[tuple[str, str]]  # (clé, libellé)
    in_baseline: bool
    # par ligne : l'étape et si elle est déplacée (None : la ligne ne l'a pas ; ligne hors de cette famille : absente du dict)
    steps: dict[int, tuple[_Step | None, bool]]
    base_row: int | None
    base_values: dict[str, _Value] | None


def _columns(base_labels: dict[str, str] | None, base_values: dict[str, _Value] | None, others: list[tuple[dict[str, _Value], dict[str, str]]]) -> list[tuple[str, str]]:
    """Les colonnes d'une étape : celles de la base dans leur ordre, puis celles des autres lignes ;
    une colonne vide partout tombe - il en reste au moins une (une étape sans paramètre : sa présence)."""
    order: dict[str, str] = {}
    for values, labels in [(base_values or {}, base_labels or {}), *others]:
        for key, label in labels.items():
            order.setdefault(key, label)
        for key in values:
            order.setdefault(key, key)
    filled = {key for values, _labels in [(base_values or {}, {}), *others] for key in values}
    columns = [(key, label) for key, label in order.items() if key in filled]
    return columns or [(PRESENT_COLUMN, "Présente")]


def _present_value(step: _Step | None) -> _Value | None:
    return _Value(("present",), "✓", "Étape présente") if step is not None else None


def _group_cells(group: _Group, row: int) -> list[dict[str, Any]]:
    if row not in group.steps:
        return [_blank(NOT_APPLICABLE) for _ in group.columns]
    step, moved = group.steps[row]
    cells = []
    for key, _label in group.columns:
        if step is None:
            cells.append(_blank(ABSENT, "Étape absente de cette structure") if group.in_baseline and row != group.base_row else _blank(EMPTY))
            continue
        value = _present_value(step) if key == PRESENT_COLUMN else step.values.get(key)
        if row == group.base_row:
            cells.append({"text": value.text if value else "—", "status": SAME, "title": value.title if value else ""})
            continue
        base = (_present_value(step) if key == PRESENT_COLUMN else (group.base_values or {}).get(key)) if group.in_baseline else None  # la base a l'étape
        status = ADDED_LAYER if not group.in_baseline else MOVED if moved else SAME
        where = f"Étape déplacée : n° {step.position + 1} ici, n° {group.position} dans la base" if moved and group.position else ""
        cells.append(_cell(value, base, status=status, moved_title=where))
    return cells


# -- le tableau ------------------------------------------------------------------------------------


def _first_with(rows: list[Compared], baseline: int, has: Any) -> int | None:
    order = [baseline, *(i for i in range(len(rows)) if i != baseline)]
    return next((i for i in order if not rows[i].error and has(rows[i])), None)


def _has_process(row: Compared) -> bool:
    return isinstance(row.process, dict)


def _process_groups(rows: list[Compared], base: int) -> list[_Group]:
    members = [i for i, row in enumerate(rows) if not row.error and _has_process(row)]
    steps_by_row = {i: _steps_of(rows[i]) for i in members}
    slots: list[_Slot] = []
    placed = {base: _place(steps_by_row[base], slots, baseline=True)}
    for i in members:
        if i != base:
            placed[i] = _place(steps_by_row[i], slots, baseline=False)

    substrates = {i: _substrate((rows[i].process or {}).get("substrate")) for i in members}
    base_sub_values, base_sub_labels = substrates[base]
    groups = [
        _Group(
            SUBSTRATE_KEY,
            "Substrat",
            SUBSTRATE_KEY,
            "Substrat",
            None,
            _columns(base_sub_labels, base_sub_values, [substrates[i] for i in members if i != base]),
            True,
            {i: (_Step(None, SUBSTRATE_KEY, "Substrat", (SUBSTRATE_KEY, ""), substrates[i][0], substrates[i][1], -1), False) for i in members},
            base,
            base_sub_values,
        )
    ]
    base_positions = {id(slot): n for n, slot in enumerate(s for s in slots if s.in_baseline)}
    for n, slot in enumerate(slots):
        row_steps = {i: placed[i].get(id(slot), (None, False)) for i in members}
        base_step = row_steps[base][0] if slot.in_baseline else None
        others = [(step.values, step.labels) for i, (step, _moved) in row_steps.items() if step is not None and i != base]
        groups.append(
            _Group(
                f"step-{n}",
                slot.first.name if base_step is None else base_step.name,
                slot.first.kind,
                STEP_KIND_LABELS.get(slot.first.kind, slot.first.kind),
                base_positions.get(id(slot), -1) + 1 if slot.in_baseline else None,
                _columns(base_step.labels if base_step else None, base_step.values if base_step else None, others),
                slot.in_baseline,
                row_steps,
                base,
                base_step.values if base_step else None,
            )
        )
    return groups


def _declared_group(rows: list[Compared], base: int) -> _Group:
    """Le split déclaré d'une étude sans structure : une colonne par facteur, une ligne par plaque."""
    members = [i for i, row in enumerate(rows) if not row.error and row.declared is not None]
    by_row: dict[int, tuple[_Step | None, bool]] = {}
    for i in members:
        factors, values = rows[i].declared or ([], [])
        labels = {f"factor:{name}": name for name in factors}
        found = {f"factor:{name}": _Value(("text", value), value) for name, value in zip(factors, values) if str(value).strip()}
        by_row[i] = (_Step(None, DECLARED_KEY, "Split déclaré", (DECLARED_KEY, ""), found, labels, -1), False)
    base_step = by_row[base][0]
    assert base_step is not None
    others = [(step.values, step.labels) for i, (step, _m) in by_row.items() if step is not None and i != base]
    return _Group(
        DECLARED_KEY,
        "Split déclaré",
        DECLARED_KEY,
        "Sans structure",
        None,
        _columns(base_step.labels, base_step.values, others),
        True,
        by_row,
        base,
        base_step.values,
    )


def _counts(cells: list[dict[str, Any]], groups: list[_Group], row: int) -> dict[str, int]:
    """Ce qui distingue une ligne de la base : paramètres modifiés, paramètres ajoutés, couches en
    plus, étapes déplacées et couches absentes (une étape compte une fois, pas une fois par colonne)."""
    counts = {"changed": 0, "added_params": 0, "added_layers": 0, "moved_layers": 0, "absent_layers": 0}
    start = 0
    for group in groups:
        mine = cells[start : start + len(group.columns)]
        start += len(group.columns)
        statuses = {cell["status"] for cell in mine}
        counts["changed"] += sum(1 for cell in mine if cell["status"] == CHANGED or cell.get("changed"))
        counts["added_params"] += sum(1 for cell in mine if cell["status"] == ADDED_PARAM)
        counts["added_layers"] += ADDED_LAYER in statuses
        counts["moved_layers"] += MOVED in statuses
        counts["absent_layers"] += ABSENT in statuses
    return counts


def _retouches(base: Compared, row: Compared) -> list[str]:
    """Ce qui change sans toucher aux paramètres : les étapes renommées et les étiquettes de couches
    (et leur regroupement par brique) - une retouche, sans nouveau numéro de version."""
    if base.metadata is None or row.metadata is None or base.metadata is row.metadata:
        return []
    args = (base.metadata, row.metadata, base.step_ids or None, row.step_ids or None)
    return [change["line"] for change in (*kinds.describe_step_changes(*args), *kinds.describe_label_changes(*args))]


def build(rows: list[Compared], baseline: int = 0) -> dict[str, Any]:
    """Le tableau de ``rows`` comparées à la ligne ``baseline`` : ``{baseline, rows, groups,
    summary}``. ``groups`` : le substrat, puis une entrée par étape (celles de la base dans leur
    ordre, celles qu'une autre ligne ajoute à leur place) - ``{key, label, kind, kind_label,
    position, status, differs, columns: [{key, label, status, differs}]}`` ; un split déclaré a le
    sien. Chaque ligne : ce qui la nomme, ``baseline``, ``cells`` (une par colonne, dans l'ordre des
    groupes : ``{text, status, title, changed?}``, ou ``None`` pour une ligne sans rien à comparer -
    ``note`` ou ``error`` dit pourquoi), ``notes`` (les retouches face à la base) et ``summary``.

    La base des étapes est la ligne ``baseline`` si elle a un procédé, sinon la première qui en a
    un ; celle d'un split déclaré, de même."""
    if not rows:
        return {"baseline": None, "rows": [], "groups": [], "summary": _empty_summary()}
    baseline = baseline if 0 <= baseline < len(rows) else 0
    groups: list[_Group] = []
    process_base = _first_with(rows, baseline, _has_process)
    if process_base is not None:
        groups.extend(_process_groups(rows, process_base))
    declared_base = _first_with(rows, baseline, lambda row: row.declared is not None)
    if declared_base is not None:
        groups.append(_declared_group(rows, declared_base))

    payload_rows = []
    for i, row in enumerate(rows):
        comparable = not row.error and (_has_process(row) or row.declared is not None)
        cells = [cell for group in groups for cell in _group_cells(group, i)] if comparable else None
        base_row = rows[process_base] if process_base is not None and _has_process(row) else None
        payload_rows.append(
            {
                "item": row.item,
                "source": row.source,
                "label": row.label,
                "version": row.version,
                "sublabel": row.sublabel,
                "context": row.context,
                "url": row.url,
                "structure_kind": row.structure_kind,
                "wafers": row.wafers,
                "badge": row.badge,
                "baseline": i == baseline,
                "note": None if comparable or row.error else (row.note or "Rien à comparer paramètre par paramètre."),
                "error": row.error,
                "cells": cells,
                "notes": _retouches(base_row, row) if base_row is not None and base_row is not row else [],
                "summary": _counts(cells, groups, i) if cells is not None and i != baseline else _empty_summary(),
            }
        )

    payload_groups = []
    start = 0
    for group in groups:
        width = len(group.columns)
        columns = []
        for offset, (key, label) in enumerate(group.columns):
            statuses = [r["cells"][start + offset]["status"] for r in payload_rows if r["cells"] is not None]
            changed = any(r["cells"][start + offset].get("changed") for r in payload_rows if r["cells"] is not None)
            column_status = ADDED_PARAM if ADDED_PARAM in statuses else None
            columns.append({"key": key, "label": label, "status": column_status, "differs": changed or any(s in _DIFFERENCES for s in statuses)})
        moved = any(step is not None and is_moved for step, is_moved in group.steps.values())
        payload_groups.append(
            {
                "key": group.key,
                "label": group.label,
                "kind": group.kind,
                "kind_label": group.kind_label,
                "position": group.position,
                "status": ADDED_LAYER if not group.in_baseline else MOVED if moved else None,
                "differs": any(column["differs"] for column in columns),
                "columns": columns,
            }
        )
        start += width

    summary = _empty_summary()
    for row in payload_rows:
        for key, count in row["summary"].items():
            summary[key] += count
    summary["added_params"] = sum(1 for group in payload_groups for column in group["columns"] if column["status"] == ADDED_PARAM)
    summary["added_layers"] = sum(1 for group in payload_groups if group["status"] == ADDED_LAYER)
    return {"baseline": baseline, "rows": payload_rows, "groups": payload_groups, "summary": summary}


def _empty_summary() -> dict[str, int]:
    return {"changed": 0, "added_params": 0, "added_layers": 0, "moved_layers": 0, "absent_layers": 0}
