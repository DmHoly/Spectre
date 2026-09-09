"""The cross-microproject atlas: one endpoint aggregating every microproject a user belongs to into the
payload the client-side D3 force graph draws (see ``static/js/atlas.js``). Unlike every other
router in this package, routes here are not scoped under ``/api/microprojets/{slug}`` - this is
deliberately the one page that looks across microprojects at once, not into a single one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core import atlas as atlas_core
from ..core import links, microprojects
from ..core.accounts import User
from .deps import get_current_user

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


@router.get("")
def get_atlas(user: User = Depends(get_current_user)) -> dict:
    memberships = microprojects.list_for_user(user.id)
    microproject_nodes = []
    for microproject, role in memberships:
        repo = microprojects.get_repository(microproject.slug)
        tips = microprojects.branch_tips(repo)
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
                "attachments": atlas_core.attachments_for(exp),
            }
            for exp in tips
        ]
        microproject_nodes.append(
            {
                "slug": microproject.slug,
                "name": microproject.name,
                "description": microproject.description,
                "role": role,
                "experiences": experiences,
                "edges": [{"from": a, "to": b} for a, b in edges],
            }
        )

    # Cross-microproject links - only ever surfaced when the viewer currently has access to both
    # sides, so the atlas never names a microproject or study they can no longer see (e.g. removed
    # from it since the link was made). Denormalized to slug/name here (rather than the raw
    # microproject_a_id/microproject_b_id spectre.core.links stores) so the client never needs a second
    # lookup to render or draw one.
    visible_ids = {microproject.id for microproject, _role in memberships}
    visible_slugs = {microproject.slug for microproject, _role in memberships}
    microproject_by_id = {microproject.id: microproject for microproject, _role in memberships}
    microproject_links = [
        {
            "id": link.id,
            "a": {"slug": microproject_by_id[link.microproject_a_id].slug, "name": microproject_by_id[link.microproject_a_id].name},
            "b": {"slug": microproject_by_id[link.microproject_b_id].slug, "name": microproject_by_id[link.microproject_b_id].name},
            "note": link.note,
        }
        for link in links.list_all_microproject_links(list(visible_ids))
        if link.microproject_a_id in visible_ids and link.microproject_b_id in visible_ids
    ]
    entity_links = [
        {
            "id": link.id,
            "a": {"microproject_slug": link.a.microproject_slug, "experience_id": link.a.experience_id, "entity_index": link.a.entity_index},
            "b": {"microproject_slug": link.b.microproject_slug, "experience_id": link.b.experience_id, "entity_index": link.b.entity_index},
            "note": link.note,
        }
        for link in links.list_all_entity_links(list(visible_slugs))
        if link.a.microproject_slug in visible_slugs and link.b.microproject_slug in visible_slugs
    ]

    return {"microprojects": microproject_nodes, "microproject_links": microproject_links, "entity_links": entity_links}
