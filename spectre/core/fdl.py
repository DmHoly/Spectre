"""FDL - feuille de lancement (a JIRA ticket) : the tracking number a wafer travels with through
the line, the one people quote to find a sample again. A wafer can carry several of them (one per
run it went through), so each physical entity of an experience (``Experiment.metadata
["physical_tracking"]``, see :func:`spectre.core.structures.clean_entity_entries`) holds an
ordered list under ``"fdl"`` - only present when non-empty, so every entity recorded before this
existed reads exactly as it did.

Numbers are normalized as typed - « fdl 1234 », « FDL_1234 », « 1234 » all become ``FDL-1234``, and
any other JIRA-style key (« abc 12 ») becomes ``ABC-12`` - so the same FDL is always spelled the
same way and a search finds it. Anything else is kept as typed. The link to JIRA itself (what an
FDL contains, for wafer traceability) will come later, on top of these numbers.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

MAX_FDL_PER_ENTITY = 20

_FDL_NUMBER_RE = re.compile(r"^(?:fdl)?[\s_\-#:]*(\d{1,8})$", re.IGNORECASE)
_JIRA_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})[\s_\-#:]*(\d{1,8})$")


def normalize_fdl(text: str | None) -> str | None:
    value = " ".join((text or "").split()).strip("\"' ")
    if not value:
        return None
    match = _FDL_NUMBER_RE.match(value)
    if match:
        return f"FDL-{int(match.group(1))}"
    match = _JIRA_KEY_RE.match(value)
    if match:
        return f"{match.group(1).upper()}-{int(match.group(2))}"
    return value[:40]


def clean_fdl_list(values: Iterable[str] | None) -> list[str]:
    """Normalized, without duplicates, in the order given."""
    cleaned: list[str] = []
    for raw in values or []:
        value = normalize_fdl(raw)
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[:MAX_FDL_PER_ENTITY]


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
    from the plates index (:func:`spectre.core.plates.visible_entries`) - the current state of each
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
