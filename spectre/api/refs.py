"""Project-wide ref endpoints. Unlike ``/etiquettes``/``/preuves`` (:mod:`spectre.api.experiments`),
a ref isn't scoped to one experience: it can be forked from indefinitely, long after the experience
it names has stopped being any branch's tip, and the point is to see every one of them - and how
they connect to each other - across the whole project at once. So listing them, and their
condensed ref-to-ref graph, live at the project level, next to the atlas's own condensed view of
branch tips (:mod:`spectre.core.atlas`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core import projects
from ..core import refs as refs_core
from ..core.permissions import require_role
from ..core.projects import Project

router = APIRouter(prefix="/api/projects", tags=["refs"])


@router.get("/{slug}/refs")
def list_refs(project: Project = Depends(require_role("viewer"))) -> dict:
    repo = projects.get_repository(project.slug)
    return {"items": refs_core.list_refs(repo)}


@router.get("/{slug}/refs/graphe")
def refs_graph(project: Project = Depends(require_role("viewer"))) -> dict:
    """Refs as central nodes and the condensed edges between them - see
    :func:`spectre.core.refs.ref_graph`. The ref equivalent of the project's own version-by-version
    graph (``spectre.api.experiments.project_graph_html``): lets a caller navigate from ref to ref
    without drawing the whole lineage.
    """
    repo = projects.get_repository(project.slug)
    return refs_core.ref_graph(repo)
