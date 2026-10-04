"""The physical entities an experience tracks (``Experiment.metadata["physical_tracking"]``): one
wafer per entry - its lasermark (``sample_id``), where it is stored, and the FDL it went through
(feuilles de lancement JIRA, see :mod:`spectre.plugins.wafers.fdl`) - normalized here, on the way
in, the same way for every route that writes them.

FDL numbers are normalized as typed - « fdl 1234 », « FDL_1234 », « 1234 » all become ``FDL-1234``,
and any other JIRA-style key (« abc 12 ») becomes ``ABC-12`` - so the same FDL is always spelled the
same way and a search finds it. Anything else is kept as typed. They are only present on an entry
when non-empty, so every entity recorded before they existed reads exactly as it did.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel

MAX_FDL_PER_ENTITY = 20

_FDL_NUMBER_RE = re.compile(r"^(?:fdl)?[\s_\-#:]*(\d{1,8})$", re.IGNORECASE)
_JIRA_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,9})[\s_\-#:]*(\d{1,8})$")


class EntityTrackingInput(BaseModel):
    sample_id: str | None = None
    location: str | None = None
    fdl: list[str] = []  # FDL (JIRA launch sheets) this wafer went through - see spectre.plugins.wafers.fdl


def compact(text: str | None) -> str:
    """A lasermark as compared: case, spaces and separators ignored (« w12-a3 » = « W12 A3 »)."""
    return re.sub(r"[\s_\-./#:]", "", text or "").upper()


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


def clean_entity_entries(entities: list[Any]) -> list[dict[str, Any]]:
    """Normalize a list of entity-tracking inputs (each with a ``sample_id``/``location``/``fdl``
    attribute) into the plain dict shape stored in ``Experiment.metadata["physical_tracking"]`` -
    blank strings become ``None``, the same cleanup ``spectre.plugins.experiments.api::set_physical_tracking``
    already applied locally before this was shared with the launch routes. A wafer's FDLs
    (JIRA launch sheets) are normalized (:func:`clean_fdl_list`) and kept under ``"fdl"`` - only
    when there is at least one, so an entity without any reads exactly as before.
    """

    def _clean(value: str | None) -> str | None:
        return value.strip() or None if value else None

    cleaned = []
    for e in entities:
        entry: dict[str, Any] = {"sample_id": _clean(e.sample_id), "location": _clean(e.location)}
        fdl = clean_fdl_list(getattr(e, "fdl", None))
        if fdl:
            entry["fdl"] = fdl
        cleaned.append(entry)
    return cleaned


def has_tracked_physical_entity(metadata: dict[str, Any]) -> bool:
    """Whether at least one physical entity (a real sample identifier, not just a blank tracking
    slot) has ever been recorded on this experience - every experience must be traceable to
    something physical, checked when it's created and enforced again before it can be concluded.
    """
    return any(entry.get("sample_id") for entry in metadata.get("physical_tracking", []))


def entities_for(experiment: Any) -> list[dict]:
    """The physical entities worth showing as their own atlas node - entries that carry no
    ``sample_id``/``location`` at all (the common case: most experiments never fill this in)
    don't get a point, there'd be nothing to show or label. ``index`` is the entry's position in
    the *raw* ``physical_tracking`` list, not in this (filtered, so potentially shorter) returned
    one - the addressing :mod:`spectre.plugins.links.service` and attachments both use, so it has to
    survive a campaign with some variants tracked and others still blank rather than silently
    compacting and pointing a link/attachment at the wrong sample.
    """
    return [
        {
            "index": i,
            "sample_id": entry.get("sample_id"),
            "location": entry.get("location"),
            **({"fdl": entry["fdl"]} if entry.get("fdl") else {}),
        }
        for i, entry in enumerate(experiment.metadata.get("physical_tracking", []))
        if entry.get("sample_id") or entry.get("location") or entry.get("fdl")
    ]
