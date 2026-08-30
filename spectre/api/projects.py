"""Projects and membership: the only "who can see/do what" concept in Spectre. Every other
router (structures, experiments) sits behind :func:`spectre.core.permissions.require_role` for a
project resolved here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import projects
from ..core.accounts import User
from ..core.permissions import require_role
from ..core.projects import Project
from .deps import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])

RUNNING_STATUSES = {"draft", "running"}
CONCLUDED_STATUSES = {"concluded", "abandoned"}


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class AddMemberRequest(BaseModel):
    email: str
    role: str


def _experiment_counts(slug: str) -> tuple[int, int]:
    repo = projects.get_repository(slug)
    running = sum(1 for exp in repo if exp.conclusion.status in RUNNING_STATUSES)
    concluded = sum(1 for exp in repo if exp.conclusion.status in CONCLUDED_STATUSES)
    return running, concluded


def _project_payload(project: Project, role: str) -> dict:
    running, concluded = _experiment_counts(project.slug)
    return {
        "id": project.id,
        "slug": project.slug,
        "name": project.name,
        "description": project.description,
        "role": role,
        "running_count": running,
        "concluded_count": concluded,
    }


@router.get("")
def list_projects(user: User = Depends(get_current_user)) -> list[dict]:
    return [_project_payload(project, role) for project, role in projects.list_for_user(user.id)]


@router.post("", status_code=201)
def create_project(body: CreateProjectRequest, user: User = Depends(get_current_user)) -> dict:
    try:
        project = projects.create(body.name, body.description, owner_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _project_payload(project, "owner")


@router.get("/{slug}")
def get_project(project: Project = Depends(require_role("viewer")), user: User = Depends(get_current_user)) -> dict:
    role = projects.role_for(project.id, user.id)
    return _project_payload(project, role)


@router.get("/{slug}/members")
def list_members(project: Project = Depends(require_role("viewer"))) -> list[dict]:
    return projects.list_members(project.id)


@router.post("/{slug}/members", status_code=201)
def add_member(
    body: AddMemberRequest, project: Project = Depends(require_role("owner")), user: User = Depends(get_current_user)
) -> dict:
    try:
        status = projects.add_member(project.id, project.name, body.email, body.role, invited_by=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": status, "members": projects.list_members(project.id), "invitations": projects.list_invitations(project.id)}


@router.get("/{slug}/invitations")
def list_invitations(project: Project = Depends(require_role("owner"))) -> list[dict]:
    return projects.list_invitations(project.id)


@router.delete("/{slug}/invitations/{token}")
def cancel_invitation(token: str, project: Project = Depends(require_role("owner"))) -> list[dict]:
    projects.cancel_invitation(project.id, token)
    return projects.list_invitations(project.id)


@router.delete("/{slug}/members/{user_id}")
def remove_member(user_id: int, project: Project = Depends(require_role("owner"))) -> list[dict]:
    if user_id == project.created_by:
        raise HTTPException(status_code=400, detail="impossible de retirer la personne qui a créé le projet")
    projects.remove_member(project.id, user_id)
    return projects.list_members(project.id)


@router.delete("/{slug}")
def delete_project(confirm_name: str, project: Project = Depends(require_role("owner"))) -> dict:
    """Irreversible: deletes the project's database rows and its whole on-disk Follow repository
    (every experiment's history). ``confirm_name`` must match the project's name exactly - the
    frontend already asks the owner to type it, this is the same guard enforced server-side so a
    raw API call can't skip it.
    """
    if confirm_name.strip() != project.name:
        raise HTTPException(status_code=422, detail="le nom saisi ne correspond pas au nom du projet")
    projects.delete(project)
    return {"status": "ok"}
