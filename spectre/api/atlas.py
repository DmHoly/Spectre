"""The cross-project atlas: one endpoint aggregating every project a user belongs to into the
payload the client-side D3 force graph draws (see ``static/js/atlas.js``). Unlike every other
router in this package, routes here are not scoped under ``/api/projects/{slug}`` - this is
deliberately the one page that looks across projects at once, not into a single one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core import atlas as atlas_core
from ..core import links, projects
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


@router.get("")
def get_atlas(user: User = Depends(get_current_user)) -> dict:
    memberships = projects.list_for_user(user.id)
    project_nodes = []
    for project, role in memberships:
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

    # Cross-project links - only ever surfaced when the viewer currently has access to both
    # sides, so the atlas never names a project or study they can no longer see (e.g. removed
    # from it since the link was made). Denormalized to slug/name here (rather than the raw
    # project_a_id/project_b_id spectre.core.links stores) so the client never needs a second
    # lookup to render or draw one.
    visible_ids = {project.id for project, _role in memberships}
    visible_slugs = {project.slug for project, _role in memberships}
    project_by_id = {project.id: project for project, _role in memberships}
    project_links = [
        {
            "id": link.id,
            "a": {"slug": project_by_id[link.project_a_id].slug, "name": project_by_id[link.project_a_id].name},
            "b": {"slug": project_by_id[link.project_b_id].slug, "name": project_by_id[link.project_b_id].name},
            "note": link.note,
        }
        for link in links.list_all_project_links(list(visible_ids))
        if link.project_a_id in visible_ids and link.project_b_id in visible_ids
    ]
    entity_links = [
        {
            "id": link.id,
            "a": {"project_slug": link.a.project_slug, "experience_id": link.a.experience_id, "entity_index": link.a.entity_index},
            "b": {"project_slug": link.b.project_slug, "experience_id": link.b.experience_id, "entity_index": link.b.entity_index},
            "note": link.note,
        }
        for link in links.list_all_entity_links(list(visible_slugs))
        if link.a.project_slug in visible_slugs and link.b.project_slug in visible_slugs
    ]

    return {"projects": project_nodes, "project_links": project_links, "entity_links": entity_links}
