"""FDL - feuille de lancement (a JIRA ticket) : the tracking number a wafer travels with through
the line, the one people quote to find a sample again. A wafer can carry several of them (one per
run it went through), so each physical entity of an experience (``Experiment.metadata
["physical_tracking"]``) holds an ordered list under ``"fdl"``, normalized on the way in (see
:mod:`spectre.plugins.experiments.entities`).

This module finds them again: how well an FDL matches what was typed in the search bar. The link to
JIRA itself (what an FDL contains, for wafer traceability) will come later, on top of these numbers.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..experiments.entities import normalize_fdl


def _compact(text: str) -> str:
    return re.sub(r"[\s_\-#:]", "", text or "").upper()


def rank(query: str, value: str) -> int | None:
    """How ``value`` matches ``query`` : 0 for the exact number (« 1234 » finds FDL-1234), 1 for a
    number containing what was typed, ``None`` otherwise - and always ``None`` without a digit, an
    FDL being a number."""
    if not re.search(r"\d", query or ""):
        return None
    if value == normalize_fdl(query):
        return 0
    fragment = _compact(query)
    return 1 if fragment and fragment in _compact(value) else None


def best_rank(query: str, values: Iterable[str]) -> int | None:
    ranks = [r for r in (rank(query, value) for value in values) if r is not None]
    return min(ranks) if ranks else None
