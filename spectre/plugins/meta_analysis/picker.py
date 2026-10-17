"""Choisir les plaques d'une analyse sans connaître leur lasermark : ce qu'on tape se cherche comme dans la barre
du haut - un lasermark (ou un ancien nom), un run d'épitaxie, un lot, un µprojet, une FDL - et chaque réponse est
un groupe de plaques qu'on ajoute d'un coup ou une à une.

- les plaques dont le lasermark répond ;
- un groupe par run d'épitaxie, par lot (lot de Spectre ou lot JIRA lu en ligne) et par ancien nom qui répond -
  la recherche des plaques (:func:`spectre.plugins.wafers.service.wafers`) dit ce qui a répondu pour chacune ;
- un groupe par µprojet qui répond (son numéro ou son nom, parmi ceux qu'on peut connaître) : ses plaques ;
- dès qu'on tape un chiffre, les plaques dont une FDL répond.
"""

from __future__ import annotations

import re
from typing import Any

from ..accounts.service import User
from ..microprojects import service as microprojects
from ..wafers import links, records, service as wafers, tracking

MAX_GROUPS = 12
MAX_WAFERS_PER_GROUP = 40
MAX_MICROPROJECTS = 5
MAX_NAMED = 3  # au-delà, les runs (lots, anciens noms) qui répondent ne font qu'un groupe
KIND_ORDER = {"wafer": 0, "run": 1, "lot": 2, "name": 3, "microproject": 4, "fdl": 5}


def _item(wafer: dict[str, Any]) -> dict[str, Any]:
    """Une plaque proposée : son lasermark, et de quoi la reconnaître (son run, sa dernière étude ou sa fiche)."""
    latest = wafer["latest"]
    experiment = (latest or {}).get("experiment") or {}
    runs = wafer.get("run_names") or []
    matched, kind = wafer.get("matched_alias"), wafer.get("matched_kind")
    found_by = {"run": f"run {matched}", "lot": f"lot {matched}", "name": f"ex-{matched}"}.get(kind) if matched else None
    detail = " · ".join(
        part
        for part in (
            found_by or (f"run {runs[0]}" if runs else ""),
            experiment.get("title") or (experiment.get("microproject") or {}).get("code") or "" if latest else "fiche de plaque, sans étude",
        )
        if part
    )
    return {"key": wafer["key"], "lasermark": wafer["lasermark"], "detail": detail}


def _group(kind: str, label: str, detail: str, found: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": kind, "label": label, "detail": detail, "total": len(found), "wafers": [_item(w) for w in found[:MAX_WAFERS_PER_GROUP]]}


def search(user: User, query: str) -> dict[str, Any]:
    """``{groups: [{kind, label, detail, total, wafers: [{key, lasermark, detail}]}]}`` - ``kind`` : wafer (les
    plaques dont le lasermark répond), run, lot, name (un ancien nom), microproject, fdl ; ``total`` : toutes les
    plaques du groupe, dont ``wafers`` montre les :data:`MAX_WAFERS_PER_GROUP` premières."""
    query = " ".join(query.split())
    if len(wafers.wafer_key(query)) < 2:
        return {"groups": []}
    occurrences = wafers.occurrences(user)
    line = tracking.line_facts()
    context = {"records": records.all_records(), "line": line, "aliases": links.aliases(), "lots": wafers.lot_names_index(line)}
    groups: list[dict[str, Any]] = []

    direct: list[dict[str, Any]] = []
    by_alias: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for wafer in wafers.wafers(occurrences, q=query, **context):
        if wafer["matched_alias"]:
            by_alias.setdefault((wafer["matched_kind"] or "name", wafer["matched_alias"]), []).append(wafer)
        else:
            direct.append(wafer)
    if direct:
        groups.append(_group("wafer", "Plaques", "dont le lasermark répond", direct))
    words = {"run": ("run d'épitaxie", "runs d'épitaxie"), "lot": ("lot", "lots"), "name": ("ancien nom", "anciens noms")}
    for kind, (one, many) in words.items():
        named = [(name, found) for (k, name), found in by_alias.items() if k == kind]
        if len(named) > MAX_NAMED:
            # « M105 » : une douzaine de runs d'une plaque chacun - un seul groupe, chaque plaque dit son run
            found = [w for _name, ws in named for w in ws]
            groups.append(_group(kind, f"{query}…", f"{len(named)} {many} qui commencent ou contiennent « {query} »", found))
        else:
            groups.extend(_group(kind, name, one, found) for name, found in named)

    for microproject in microprojects.visible(user, microprojects.search(query, limit=MAX_MICROPROJECTS * 4))[:MAX_MICROPROJECTS]:
        found = wafers.wafers(wafers.occurrences(user, microproject=microproject))
        if found:
            groups.append(_group("microproject", microproject.code or microproject.name, microproject.name if microproject.code else "µprojet", found))

    if re.search(r"\d", query):
        number = re.sub(r"^\s*fdl[\s_\-#:]*", "", query, flags=re.IGNORECASE)
        found = wafers.wafers(occurrences, fdl=number, records=context["records"], line=line)
        if found:
            groups.append(_group("fdl", f"FDL {number}", "les plaques qui portent cette FDL", found))

    groups.sort(key=lambda g: KIND_ORDER.get(g["kind"], 9))
    return {"groups": groups[:MAX_GROUPS]}
