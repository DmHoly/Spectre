"""The cross-project atlas: one endpoint aggregating every project a user belongs to into the
payload the client-side D3 force graph draws (see ``static/js/atlas.js``). Unlike every other
router in this package, routes here are not scoped under ``/api/projects/{slug}`` - this is
deliberately the one page that looks across projects at once, not into a single one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core import atlas as atlas_core
from ..core import projects
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


@router.get("")
def get_atlas(user: User = Depends(get_current_user)) -> dict:
    project_nodes = []
    for project, role in projects.list_for_user(user.id):
        repo = projects.get_repository(project.slug)
        tips = projects.branch_tips(repo)
        edges = atlas_core.condensed_edges(repo, tips)
        experiences = [
            {
                "id": exp.id,
                "title": exp.title,
                "intent": exp.intent,
                "branch": exp.branch,
                "status": exp.conclusion.status,
                "conclusion_summary": exp.conclusion.summary,
                "objectives": atlas_core.objective_statuses(exp),
                "entities": atlas_core.entities_for(exp),
            }
            for exp in tips
        ]
        project_nodes.append(
            {
                "slug": project.slug,
                "name": project.name,
                "description": project.description,
                "role": role,
                "experiences": experiences,
                "edges": [{"from": a, "to": b} for a, b in edges],
            }
        )
    return {"projects": project_nodes}
