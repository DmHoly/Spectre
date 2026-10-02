"""FDL - feuille de lancement (a JIRA ticket) : the tracking number a wafer travels with through
the line, the one people quote to find a sample again. A wafer can carry several of them (one per
run it went through), so each physical entity of an experience (``Experiment.metadata
["physical_tracking"]``) holds an ordered list under ``"fdl"``, normalized on the way in (see
:mod:`spectre.plugins.experiments.entities`).

This module finds them again: every FDL of an experience, and the experiences whose wafers carry
the one typed in the search bar. The link to JIRA itself (what an FDL contains, for wafer
traceability) will come later, on top of these numbers.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..experiments.entities import normalize_fdl


def fdls_of(physical_tracking: list[dict[str, Any]]) -> list[str]:
    """Every FDL of an experience's entities, in order, each once."""
    seen: list[str] = []
    for entry in physical_tracking or []:
        for value in entry.get("fdl") or []:
            if value not in seen:
                seen.append(value)
    return seen


def _compact(text: str) -> str:
    return re.sub(r"[\s_\-#:]", "", text or "").upper()


def search(query: str, rows: Iterable[tuple[Any, dict[str, Any]]], *, limit: int = 8) -> list[dict]:
    """Experiences whose plates carry an FDL matching ``query`` - the exact number first (« 1234 »
    finds FDL-1234), then numbers containing what was typed. ``rows`` yields ``(microproject, entry)``
    from the plates index (:func:`spectre.plugins.wafers.service.visible_entries`) - the current state of each
    line of study, in the microprojects the caller may see."""
    if not re.search(r"\d", query or ""):
        return []
    wanted = normalize_fdl(query)
    fragment = _compact(query)
    hits: list[tuple[int, str, dict]] = []
    for microproject, entry in rows:
        for value in entry.get("fdl") or []:
            if value == wanted:
                rank = 0
            elif fragment and fragment in _compact(value):
                rank = 1
            else:
                continue
            hits.append(
                (
                    rank,
                    value,
                    {
                        "fdl": value,
                        "sample_id": entry.get("sample_id"),
                        "experience": {k: entry["experience"][k] for k in ("id", "title", "status")},
                        "microproject": {"slug": microproject.slug, "code": microproject.code, "name": microproject.name},
                    },
                )
            )
    hits.sort(key=lambda hit: (hit[0], hit[1], hit[2]["experience"]["title"]))
    return [hit[2] for hit in hits[:limit]]
