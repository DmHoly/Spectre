"""Les routes des références de structure, sous ``/api/references`` (un objet de toute
l'application : tout compte connecté les lit) et ``/api/reference-versions`` (les versions publiées
depuis un µprojet, pour sa page d'évolution). Le domaine est dans :mod:`.service`."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from ...kernel.http import created
from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects import service as microprojects
from . import service
from .schemas import ReferenceChanges, ReferenceCreate, VersionPublish

router = APIRouter(prefix="/api", tags=["references"])


def _reference_url(slug: str) -> str:
    return f"/api/references/{quote(slug, safe='')}"


@router.get("/references")
def list_references(q: str = Query("", max_length=200), user: User = Depends(current_user)) -> list[dict]:
    """Toutes les références, la plus récemment mise à jour d'abord : chacune avec sa dernière
    version (numéro, date, µprojet source, auteur), son nombre de versions et d'usages."""
    return service.list_references(user, q)


@router.post("/references", status_code=201)
def create_reference(body: ReferenceCreate, response: Response, user: User = Depends(current_user)) -> dict:
    """Une nouvelle référence, sans version - 409 ``reference_name_taken`` pour un nom déjà pris."""
    reference = service.create_reference(user, name=body.name, description=body.description)
    created(response, _reference_url(reference.slug))
    return service.get_reference(user, reference.slug)


@router.get("/references/{reference_slug}")
def get_reference(reference_slug: str, user: User = Depends(current_user)) -> dict:
    return service.get_reference(user, reference_slug)


@router.patch("/references/{reference_slug}")
def update_reference(reference_slug: str, body: ReferenceChanges, user: User = Depends(current_user)) -> dict:
    """Renommer ou décrire (son créateur ou un admin) ; le slug ne change pas."""
    service.update_reference(user, reference_slug, body.model_dump(exclude_unset=True))
    return service.get_reference(user, reference_slug)


@router.delete("/references/{reference_slug}", status_code=204)
def delete_reference(reference_slug: str, user: User = Depends(current_user)) -> Response:
    """Retirer (son créateur ou un admin ; avec des versions, un admin seulement : 409 sinon)."""
    service.delete_reference(user, reference_slug)
    return Response(status_code=204)


@router.get("/references/{reference_slug}/versions")
def version_graph(reference_slug: str, user: User = Depends(current_user)) -> dict:
    """``{reference, lanes, nodes, edges}`` : l'évolution de la référence (:func:`service.version_graph`)."""
    return service.version_graph(user, reference_slug)


@router.post("/references/{reference_slug}/versions", status_code=201)
def publish_version(reference_slug: str, body: VersionPublish, response: Response, user: User = Depends(current_user)) -> dict:
    """Publier une version d'étude comme nouvelle version de la référence (``editor`` du µprojet
    source) - 201 + ``Location`` vers la version ; 409 si elle est identique à sa version parente."""
    number = service.publish_version(
        user,
        reference_slug,
        microproject_slug=body.microproject,
        experiment_id=body.experiment_id,
        version_id=body.version_id,
        note=body.note,
        parent=body.parent,
    )
    created(response, f"{_reference_url(reference_slug)}/versions/{number}")
    return service.get_version(user, reference_slug, number)


@router.get("/references/{reference_slug}/versions/{version_number}")
def get_version(reference_slug: str, version_number: str, user: User = Depends(current_user)) -> dict:
    """Une version (« 1.1 ») : son nœud, sa structure dessinée (``structure_svg``) et son procédé
    éditable (``process``), d'où lancer une étude."""
    return service.get_version(user, reference_slug, version_number)


@router.get("/references/{reference_slug}/versions/{version_number}/structure-diff")
def version_diff(reference_slug: str, version_number: str, against: str | None = None, user: User = Depends(current_user)) -> dict:
    """La version comparée à une autre de la même référence (``against``), sa parente par défaut :
    ``{target: {number} | null, entries, summary?, label_changes, param_changes, step_changes}``."""
    return service.version_diff(reference_slug, version_number, against)


@router.get("/reference-versions")
def versions_published_from(microproject: str, user: User = Depends(current_user)) -> list[dict]:
    """Les versions de référence publiées depuis le µprojet ``microproject`` (``viewer`` : 403
    sinon, 404 s'il n'existe pas) - les badges de sa page d'évolution."""
    found = microprojects.get_by_slug(microproject)
    microprojects.check_role(user, found, "viewer")
    return service.versions_published_from(found)
