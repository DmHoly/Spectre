"""Les plaques jumelles : celles dont la structure est celle d'une ligne de référence, à quelques
variations près.

**Une variation** est une différence que le tableau du comparateur colorerait face à la base : un
paramètre modifié ou ajouté, une couche en plus ou absente, une étape déplacée (une couche compte
pour une seule variation, quel que soit le nombre de ses paramètres) - le même décompte que le
résumé du comparateur (:func:`comparator.table.differences`). Les retouches (une étape renommée,
une étiquette) ne comptent pas : elles ne changent pas la structure.

**Quelles plaques.** Toutes celles que suit une étude de vos µprojets, chacune par la structure de
la dernière étude qui la suit (la règle de la source « plaque » du comparateur) ; une plaque qu'on ne
lit pas (µprojet dont vous n'êtes pas membre) n'est pas cherchée. Les plaques d'une même étude
(réplicats) partagent une structure : elle n'est lue et comparée qu'une fois. Une structure qui n'a
pas les colonnes de la base (un procédé face à un split déclaré, des images) n'est jamais jumelle.
"""

from __future__ import annotations

from typing import Any

from ...kernel.errors import DomainError, InvalidInput
from ..accounts.service import User
from ..comparator import service as comparator
from ..comparator.service import Compared
from ..wafers import service as wafers

MAX_VARIATIONS = 5
MAX_TWINS = 300
NOTHING_TO_COMPARE = "nothing_to_compare"


def _base_row(user: User, item: str) -> Compared:
    row = comparator.rows_for(user, [item])[0]  # une campagne : sa variante de référence d'abord
    if row.error:
        raise InvalidInput(row.error, code=NOTHING_TO_COMPARE)
    if row.process is None and row.declared is None:
        raise InvalidInput(row.note or "Cette structure n'a rien à comparer paramètre par paramètre.", code=NOTHING_TO_COMPARE)
    return row


def _structure_rows(user: User, found: list[wafers.Occurrence]) -> dict[str, Compared | None]:
    """La structure que montre chaque plaque (par clé), ``None`` quand on ne sait pas la lire. Une
    étude sans variante dans son jeton (une étude simple) a une seule structure pour tous ses
    réplicats : lue une fois."""
    by_study: dict[tuple[str, str, str], Compared | None] = {}
    by_place: dict[tuple[str, str, str, int], Compared | None] = {}
    rows: dict[str, Compared | None] = {}
    for occurrence in found:
        experiment = occurrence.entry["experiment"]
        study = (occurrence.microproject.slug, experiment["id"], experiment["version_id"])
        place = (*study, occurrence.entry["entity_index"])
        if study in by_study:
            rows[occurrence.key] = by_study[study]
            continue
        if place not in by_place:
            try:
                read: Compared | None = comparator.study_rows(user, *study, occurrence.entry["entity_index"])[0]
            except DomainError:
                read = None
            by_place[place] = read
            if read is not None and "~" not in read.item:
                by_study[study] = read
        rows[occurrence.key] = by_place[place]
    return rows


def _describe(row: Compared) -> dict[str, Any]:
    return {"item": row.item, "label": row.label, "study": row.sublabel or row.label, "microproject": row.context, "version": row.version, "url": row.url}


def find(user: User, item: str, max_variations: int = 0) -> dict[str, Any]:
    """Les plaques jumelles de la structure ``item`` (un jeton du comparateur), à ``max_variations``
    variations près : ``{base, max_variations, scanned, skipped, truncated, twins}``.

    ``base`` : la ligne de référence (``item``, ``label``, ``study``, ``microproject``, ``version``,
    ``url``) ; ``scanned`` : les plaques examinées ; ``skipped`` : celles dont la structure n'a pas
    les colonnes de la base ou n'a pu être lue ; ``twins``, les plus proches d'abord, puis les plus
    récentes : ``{item, lasermark, label, study, microproject, version, url, variations,
    differences}`` - ``item`` est le jeton ``wafer:…`` à ajouter à la comparaison, ``differences``
    les variations (:func:`comparator.table.differences`). La plaque de ``item``, si c'en est une,
    n'est pas parmi ses jumelles."""
    if not 0 <= max_variations <= MAX_VARIATIONS:
        raise InvalidInput(f"Entre 0 et {MAX_VARIATIONS} variations.", code="invalid_variations")
    base = _base_row(user, item)
    own = {wafers.wafer_key(base.label)} if base.source == "wafer" else set()

    candidates = [occurrence for key, occurrence in wafers.latest_members(wafers.occurrences(user)).items() if key not in own]
    structures = _structure_rows(user, candidates)

    verdicts: dict[str, list[dict[str, Any]]] = {}  # par structure (son jeton) : ses variations
    found: list[dict[str, Any]] = []
    skipped = 0
    for occurrence in candidates:
        row = structures[occurrence.key]
        if row is None or not comparator.comparable(base, row):
            skipped += 1
            continue
        if row.item not in verdicts:
            verdicts[row.item] = comparator.differences(comparator.compare_rows([base, row]), 1)
        differences = verdicts[row.item]
        if len(differences) > max_variations:
            continue
        sample = occurrence.entry.get("sample_id") or occurrence.key
        found.append(
            {
                **_describe(row),
                "item": f"wafer:{sample}",
                "lasermark": sample,
                "label": sample,
                "variations": len(differences),
                "differences": differences,
                "_updated_at": occurrence.updated_at,
            }
        )
    # les plus proches d'abord, puis les plus récentes, puis par lasermark (tris stables, du moins au plus important)
    found.sort(key=lambda twin: twin["lasermark"].casefold())
    found.sort(key=lambda twin: twin["_updated_at"], reverse=True)
    found.sort(key=lambda twin: twin["variations"])
    for twin in found:
        del twin["_updated_at"]
    return {
        "base": _describe(base),
        "max_variations": max_variations,
        "scanned": len(candidates),
        "skipped": skipped,
        "truncated": len(found) > MAX_TWINS,
        "twins": found[:MAX_TWINS],
    }
