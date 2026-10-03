"""Les routes des preuves d'une étude, sous ``/api/microprojects/{microproject_slug}/experiments/
{experiment_id}/evidence`` : les lire (``?version=`` pour une version passée), en ajouter une, annoter
ses images. Chaque réponse porte l'``ETag`` de la version lue ou écrite ; chaque écriture accepte
``If-Match`` (412 si la piste a avancé). Le domaine est dans :mod:`.service`.
"""

from __future__ import annotations

import follow
from fastapi import APIRouter, Depends, Header, Response

from ...kernel.http import created, etag, if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from . import service
from .schemas import AnnotationsRequest, EvidenceInput

router = APIRouter(prefix="/api/microprojects/{microproject_slug}/experiments/{experiment_id}/evidence", tags=["evidence"])


def _tag(response: Response, version: follow.Experiment) -> None:
    """L'``ETag`` de la version de la piste lue ou écrite : ce qu'une écriture suivante attend."""
    response.headers["ETag"] = etag(version.id)


@router.get("")
def list_evidence(
    experiment_id: str, response: Response, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> list[dict]:
    """Les preuves de la piste (de sa version ``version``), avec leurs liens, leurs images et leurs
    annotations."""
    read, items = service.list_evidence(microproject.slug, experiment_id, version)
    _tag(response, read)
    return items


@router.post("", status_code=201)
def add_evidence(
    experiment_id: str,
    body: EvidenceInput,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Ajoute une preuve (liens, mesure, images téléversées d'abord) : une nouvelle version de la
    piste."""
    written, evidence = service.add(microproject.slug, experiment_id, body, author=user.name, expected_version=if_match_version(if_match))
    created(response, f"/api/microprojects/{microproject.slug}/experiments/{experiment_id}/evidence/{evidence['id']}")
    _tag(response, written)
    return evidence


@router.get("/{evidence_id}")
def get_evidence(
    experiment_id: str, evidence_id: str, response: Response, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> dict:
    read, evidence = service.get_evidence(microproject.slug, experiment_id, evidence_id, version)
    _tag(response, read)
    return evidence


@router.put("/{evidence_id}/annotations")
def replace_annotations(
    experiment_id: str,
    evidence_id: str,
    body: AnnotationsRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Remplace les annotations (flèches, cadres) des images d'une preuve - renvoie la preuve."""
    written, evidence = service.set_annotations(
        microproject.slug, experiment_id, evidence_id, body.annotations, author=user.name, expected_version=if_match_version(if_match)
    )
    _tag(response, written)
    return evidence
