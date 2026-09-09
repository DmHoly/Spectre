"""Microproject-wide ref endpoints. Unlike ``/etiquettes``/``/preuves`` (:mod:`spectre.api.experiments`),
a ref isn't scoped to one experience: it can be forked from indefinitely, long after the experience
it names has stopped being any branch's tip, and the point is to see every one of them - and how
they connect to each other - across the whole microproject at once. So listing them, and their
condensed ref-to-ref graph, live at the microproject level, next to the atlas's own condensed view of
branch tips (:mod:`spectre.core.atlas`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core import microprojects
from ..core import refs as refs_core
from ..core.permissions import require_role
from ..core.microprojects import Microproject

router = APIRouter(prefix="/api/microprojets", tags=["refs"])


@router.get("/{slug}/refs")
def list_refs(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = microprojects.get_repository(microproject.slug)
    return {"items": refs_core.list_refs(repo)}


@router.get("/{slug}/refs/graphe")
def refs_graph(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """Refs as central nodes and the condensed edges between them - see
    :func:`spectre.core.refs.ref_graph`. The ref equivalent of the microproject's own version-by-version
    graph (``spectre.api.experiments.microproject_graph_html``): lets a caller navigate from ref to ref
    without drawing the whole lineage.
    """
    repo = microprojects.get_repository(microproject.slug)
    return refs_core.ref_graph(repo)
