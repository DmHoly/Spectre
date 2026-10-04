"""Les routes des études d'un µprojet, sous ``/api/microprojects/{microproject_slug}`` : une étude
est une **piste** (``experiment_id``, le nom de sa branche Follow) et ses **versions**
(``version_id``). ``GET .../experiments/{experiment_id}`` renvoie toujours la dernière version, avec
son ``ETag`` ; toute écriture accepte ``If-Match`` (412 si la piste a avancé, rien n'est écrit) et
renvoie l'étude à jour avec son nouvel ``ETag``. Le domaine est dans :mod:`.service` ; ici, on lit
la requête et on sérialise.

Le détail d'une étude ne porte que le nombre de ses preuves : elles se lisent dans le plugin evidence
(``GET .../experiments/{experiment_id}/evidence``).
La page d'une étude (``page_router``) redirige un ancien lien vers un id de version sur sa piste.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

import follow
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import RedirectResponse
from starlette.convertors import Convertor, register_url_convertor

from ...kernel.errors import Forbidden, InvalidInput, NotFound, Unauthorized
from ...kernel.http import created, etag, if_match_version
from ..accounts.deps import current_user
from ..accounts.service import User
from ..microprojects import service as microprojects
from ..microprojects.deps import get_microproject, require_role
from ..microprojects.service import Microproject
from ..structures import campaigns, kinds
from . import refs, service, versioning
from .lineage import lineage_graph
from .repository import CONCLUDED_STATUSES, RUNNING_STATUSES, branch_tips, display_status, get_repository, hold_of
from .schemas import (
    ConclusionRequest,
    CreateExperimentRequest,
    EntitiesRequest,
    EvolveRequest,
    MergeRequest,
    RefRequest,
    StatusRequest,
    StructureImagesRequest,
    TagsRequest,
)

router = APIRouter(prefix="/api/microprojects/{microproject_slug}", tags=["experiments"])
page_router = APIRouter()


def _experiment_url(slug: str, experiment_id: str) -> str:
    return f"/api/microprojects/{slug}/experiments/{experiment_id}"


# -- sérialisation ---------------------------------------------------------------------------------


def _summary(tip: follow.Experiment) -> dict:
    return {
        "id": tip.branch,
        "version_id": tip.id,
        "title": tip.title,
        "intent": tip.intent,
        "status": display_status(tip),
        "author": tip.author,
        "created_at": tip.created_at.isoformat(),
        "tags": list(tip.tags),
        # a concluded study's own summary belongs in the list too, so where it fits is clear
        # without opening it
        "conclusion_summary": tip.conclusion.summary,
    }


def _detail(slug: str, repo: follow.Repository, experiment_id: str, version: follow.Experiment) -> dict:
    continued_at = service.continued_at(repo, version)
    return {
        "id": experiment_id,
        "version_id": version.id,
        "is_tip": repo.branches.get(experiment_id) == version.id,
        "parents": list(version.parents),
        # the versions derived from this one - more than one makes it a fork point
        "children": [
            {"experiment_id": child.branch, "version_id": child.id, "title": child.title, "is_tip": repo.branches.get(child.branch) == child.id}
            for child in repo
            if version.id in child.parents
        ],
        "created_at": version.created_at.isoformat(),
        "author": version.author,
        "title": version.title,
        "intent": version.intent,
        "hypothesis": version.hypothesis,
        "context": version.metadata.get(service.CONTEXT_METADATA_KEY),
        "status": display_status(version, continued=continued_at is not None),
        "continued_at": continued_at.isoformat() if continued_at else None,
        "hold": hold_of(version),
        "objectives": [o.model_dump(mode="json") for o in version.objectives],
        "objective_verification": version.metadata.get("objective_verification", {}),
        "conclusion": version.conclusion.model_dump(mode="json"),
        "references": [r.model_dump(mode="json") for r in version.references],
        "tags": list(version.tags),
        "ref_names": refs.ref_names_for(repo, version.id),
        "structure_svg": kinds.render_structure_svg(version.structure_type, version.structure),
        "is_batch": version.structure_type == kinds.ProcessLot.registry_key(),
        # a structure given as pictures: [{image_id, kind, caption, url}, ...] in reading order
        "structure_images": kinds.structure_images_payload(slug, version.structure_type, version.structure),
        "has_editable_process": "structureforge_process" in version.metadata,
        "evidence_count": len(version.evidence),
        "physical_tracking": version.metadata.get("physical_tracking", []),
        "form_answers": dict(version.form_answers),
    }


def _respond(response: Response, slug: str, experiment_id: str, version_id: str) -> dict:
    """La version ``version_id`` de la piste, avec son ``ETag``."""
    repo = get_repository(slug)
    version = repo.get(version_id)
    response.headers["ETag"] = etag(version.id)
    return _detail(slug, repo, experiment_id, version)


def _written(response: Response, slug: str, experiment_id: str, before: str | None, after: follow.Experiment) -> dict:
    """Le résultat d'une écriture : la piste à jour (201 + ``Location`` vers la nouvelle version
    pour une évolution, 200 sinon - ``before`` est ``None`` pour une écriture qui n'en crée pas)."""
    if before is not None and after.id != before:
        created(response, f"{_experiment_url(slug, experiment_id)}/versions/{after.id}")
    elif before is not None:
        response.status_code = 200
    return _respond(response, slug, experiment_id, after.id)


# -- la collection ---------------------------------------------------------------------------------


@router.get("/experiments")
def list_experiments(
    status: Literal["all", "running", "concluded"] = "all",
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    microproject: Microproject = Depends(require_role("viewer")),
) -> dict:
    """Les pistes du µprojet (leur dernière version), les plus récentes d'abord - ``q`` cherche dans
    le titre, l'intention, les étiquettes et le nom de la piste."""
    wanted = RUNNING_STATUSES if status == "running" else CONCLUDED_STATUSES if status == "concluded" else None
    needle = q.strip().lower()
    matches = [
        tip
        for tip in branch_tips(get_repository(microproject.slug))
        if (wanted is None or tip.conclusion.status in wanted)
        and (not needle or any(needle in text.lower() for text in (tip.title, tip.intent, tip.branch, *tip.tags)))
    ]
    matches.sort(key=lambda tip: tip.created_at, reverse=True)
    return {"items": [_summary(tip) for tip in matches[offset : offset + limit]], "total": len(matches)}


@router.post("/experiments", status_code=201)
def create_experiment(
    body: CreateExperimentRequest,
    response: Response,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Une nouvelle piste (structure ``process``, ``images`` ou ``campaign``), à partir de rien ou
    d'une version existante (``from_version``)."""
    experiment = service.create(microproject.slug, body, author=user.name)
    created(response, _experiment_url(microproject.slug, experiment.branch))
    return _respond(response, microproject.slug, experiment.branch, experiment.id)


@router.get("/lineage")
def microproject_lineage(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """The microproject's structural lineage (:func:`lineage_graph`) - what the µprojet page draws.
    Only a genuine structural change creates a node (a root, a merge, or a version that actually
    moved the process forward); a status, tags or a title change updates the node of its line in
    place. Each node is a version (``version_id``) of a line of study (``experiment_id``)."""
    return lineage_graph(get_repository(microproject.slug))


@router.get("/experiment-versions/{version_id}")
def experiment_of_version(version_id: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """``{experiment_id, version_id}`` : la piste d'une version - pour un ancien lien vers un id de
    version."""
    return {"experiment_id": service.experiment_of_version(get_repository(microproject.slug), version_id), "version_id": version_id}


# -- une piste -------------------------------------------------------------------------------------


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, response: Response, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = get_repository(microproject.slug)
    tip = service.tip_of(repo, experiment_id)
    response.headers["ETag"] = etag(tip.id)
    return _detail(microproject.slug, repo, experiment_id, tip)


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(
    experiment_id: str, if_match: str | None = Header(None), microproject: Microproject = Depends(require_role("editor"))
) -> Response:
    """Supprime la piste jusqu'à son point de fourche - 409 si une autre piste en découle."""
    service.delete(microproject.slug, experiment_id, expected_version=if_match_version(if_match))
    return Response(status_code=204)


@router.get("/experiments/{experiment_id}/versions")
def list_versions(experiment_id: str, microproject: Microproject = Depends(require_role("viewer"))) -> list[dict]:
    """La frise : chaque version de la piste, de la première à la pointe (``is_tip``), avec son
    numéro X.Y.Z et son niveau de changement (``change_level`` : ``none`` pour une version qui ne
    change pas la structure - une étiquette, une preuve...)."""
    history = service.history_of(get_repository(microproject.slug), experiment_id)
    numbers = versioning.compute_branch_versions(history)
    return [
        {
            "version_id": version.id,
            "experiment_id": version.branch,
            "title": version.title,
            "intent": version.intent,
            "created_at": version.created_at.isoformat(),
            "author": version.author,
            "is_tip": i == len(history) - 1,
            "version": numbers[version.id]["version"],
            "change_level": numbers[version.id]["level"],
        }
        for i, version in enumerate(history)
    ]


@router.post("/experiments/{experiment_id}/versions", status_code=201)
def evolve_experiment(
    experiment_id: str,
    body: EvolveRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Une nouvelle version de la piste (structure ``process`` ou ``images``, intention reposée) -
    201 et ``Location`` vers la version, ou 200 si rien n'a changé."""
    before = service.tip_of(get_repository(microproject.slug), experiment_id).id
    expected = if_match_version(if_match)
    after = service.evolve(microproject.slug, experiment_id, body, author=user.name, expected_version=expected)
    return _written(response, microproject.slug, experiment_id, expected or before, after)


@router.get("/experiments/{experiment_id}/versions/{version_id}")
def get_version(experiment_id: str, version_id: str, response: Response, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    repo = get_repository(microproject.slug)
    version = service.version_of(repo, experiment_id, version_id)
    response.headers["ETag"] = etag(version.id)
    return _detail(microproject.slug, repo, experiment_id, version)


@router.put("/experiments/{experiment_id}/structure-images")
def replace_structure_images(
    experiment_id: str,
    body: StructureImagesRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    after = service.replace_structure_images(
        microproject.slug, experiment_id, body.images, author=user.name, expected_version=if_match_version(if_match)
    )
    return _written(response, microproject.slug, experiment_id, None, after)


@router.put("/experiments/{experiment_id}/conclusion")
def conclude_experiment(
    experiment_id: str,
    body: ConclusionRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    after = service.conclude(microproject.slug, experiment_id, body, author=user.name, expected_version=if_match_version(if_match))
    return _written(response, microproject.slug, experiment_id, None, after)


@router.put("/experiments/{experiment_id}/status")
def set_status(
    experiment_id: str,
    body: StatusRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Brouillon, en cours, en pause (``hold_reason``) - ou la reprise d'une étude conclue."""
    after = service.set_status(
        microproject.slug,
        experiment_id,
        status=body.status,
        hold_reason=body.hold_reason,
        author=user.name,
        expected_version=if_match_version(if_match),
    )
    return _written(response, microproject.slug, experiment_id, None, after)


@router.put("/experiments/{experiment_id}/tags")
def set_tags(
    experiment_id: str,
    body: TagsRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    after = service.set_tags(microproject.slug, experiment_id, body.tags, author=user.name, expected_version=if_match_version(if_match))
    return _written(response, microproject.slug, experiment_id, None, after)


@router.put("/experiments/{experiment_id}/entities")
def set_entities(
    experiment_id: str,
    body: EntitiesRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Les échantillons physiques suivis : un par variante d'une campagne, un sinon."""
    after = service.set_entities(
        microproject.slug, experiment_id, body.entities, author=user.name, expected_version=if_match_version(if_match)
    )
    return _written(response, microproject.slug, experiment_id, None, after)


@router.post("/experiments/{experiment_id}/merges", status_code=201)
def merge_experiments(
    experiment_id: str,
    body: MergeRequest,
    response: Response,
    if_match: str | None = Header(None),
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Réunit l'autre piste dans celle-ci : une nouvelle version à deux parents (``Location`` vers elle)."""
    after = service.merge(
        microproject.slug, experiment_id, body.other_experiment_id, author=user.name, expected_version=if_match_version(if_match)
    )
    created(response, f"{_experiment_url(microproject.slug, experiment_id)}/versions/{after.id}")
    return _respond(response, microproject.slug, experiment_id, after.id)


@router.get("/experiments/{experiment_id}/process")
def experiment_process(
    experiment_id: str, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> dict:
    """Le procédé éditable (substrat et étapes) d'une version - la pointe par défaut. Chaque étape
    porte son ``id`` stable (:func:`service.step_ids_of`), que le constructeur renvoie à l'évolution."""
    process = service.editable_process(service.version_of(get_repository(microproject.slug), experiment_id, version))
    if process is None:
        raise NotFound("Cette expérience n'a pas de procédé éditable enregistré.", code="no_process")
    return process


@router.get("/experiments/{experiment_id}/structure-diff")
def structure_diff(
    experiment_id: str,
    version: str | None = None,
    against_version: str | None = None,
    against_experiment: str | None = None,
    against_microproject: str | None = None,
    microproject: Microproject = Depends(require_role("viewer")),
    user: User = Depends(current_user),
) -> dict:
    """La structure d'une version (la pointe par défaut) comparée à une autre : une version de la
    même piste (``against_version``), la pointe ou une version d'une autre piste
    (``against_experiment``), d'un autre µprojet au besoin (``against_microproject``, lisible par
    l'appelant). Sans rien : la version de structure précédente (:func:`service.structural_baseline`).
    ``{target: {experiment_id, version_id, title, microproject} | null, entries, summary?}``."""
    repo = get_repository(microproject.slug)
    base = service.version_of(repo, experiment_id, version)
    target_repo, target_microproject = repo, None
    if against_microproject and against_microproject != microproject.slug:
        if not against_experiment:
            raise InvalidInput("Choisissez l'expérience de l'autre µprojet à comparer.", code="against_experiment_required")
        other = get_microproject(against_microproject)
        if microprojects.role_for(other.id, user.id) is None:
            raise Forbidden("Vous n'avez pas accès à cet autre µprojet.")
        target_repo, target_microproject = get_repository(other.slug), other
    if against_experiment:
        target = service.version_of(target_repo, against_experiment, against_version)
    elif against_version:
        target = service.version_of(repo, experiment_id, against_version)
    else:
        target = service.structural_baseline(repo, base)
    if target is None:
        return {"target": None, "entries": []}
    return {
        "target": {
            "experiment_id": against_experiment or experiment_id,
            "version_id": target.id,
            "title": target.title,
            "microproject": target_microproject.name if target_microproject else None,
        },
        **service.structure_diff(target, base),
    }


@router.get("/experiments/{experiment_id}/variants")
def experiment_variants(
    experiment_id: str, version: str | None = None, microproject: Microproject = Depends(require_role("viewer"))
) -> dict:
    """The constant/varying split of a DOE campaign's variants (``follow.doe.batch.analyze_batch``,
    what Follow's own GUI calls "matrice de split"), one drawn cross-section per variant, and what
    was varied in plain terms (recorded at launch) - for a campaign only."""
    experiment = service.version_of(get_repository(microproject.slug), experiment_id, version)
    if experiment.structure_type != kinds.ProcessLot.registry_key():
        raise InvalidInput("Cette expérience n'est pas une campagne à plusieurs variantes.", code="not_a_campaign")
    lot = kinds.ProcessLot.model_validate(experiment.structure)
    variation = campaigns.analyze_variants(lot.entries)
    payload: dict[str, Any] = variation.model_dump(mode="json")
    payload["svgs"] = kinds.render_lot_svgs(lot)
    payload["factor_labels"] = experiment.metadata.get("campaign_factor_labels", [])
    payload["factor_values"] = experiment.metadata.get("campaign_factor_values", [])
    payload["factor_scales"] = experiment.metadata.get("campaign_factor_scales", [])
    payload["labels"] = experiment.metadata.get("campaign_labels") or [f"#{i + 1}" for i in range(variation.entity_count)]
    payload["physical_tracking"] = experiment.metadata.get("physical_tracking", [])
    return payload


# -- les refs --------------------------------------------------------------------------------------


@router.get("/refs")
def list_refs(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    """``{refs, edges}`` : chaque ref du µprojet (des points de départ nommés) et leur graphe
    condensé, de ref en ref (:func:`spectre.plugins.experiments.refs.ref_graph`)."""
    return refs.ref_graph(get_repository(microproject.slug))


@router.post("/refs", status_code=201)
def create_ref(body: RefRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    """Marque une version (la pointe de la piste par défaut) comme ref : ``name`` (un surnom), ou
    « ref vX.Y.Z ». 422 pour un nom avec « / », 409 pour un nom déjà pris."""
    return service.create_ref(microproject.slug, body.experiment_id, body.version_id, body.name)


# -- la page d'une étude ---------------------------------------------------------------------------


class _VersionIdConvertor(Convertor):
    """Un segment d'URL qui a la forme d'un id de version (``exp_<16 hex>``) - qu'aucun nom de piste
    ne peut avoir (:data:`service.VERSION_ID_RE`)."""

    regex = "exp_[0-9a-f]{16}"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("experiment_version", _VersionIdConvertor())


@page_router.get("/microprojets/{slug}/experiences/{version_id:experiment_version}")
def legacy_version_page(slug: str, version_id: str, request: Request) -> RedirectResponse:
    """Un ancien lien vers la page d'une étude portait l'id d'une version : redirigé vers la page de
    sa piste (``?version=`` quand ce n'est pas la dernière). Hors session : la connexion d'abord."""
    try:
        user = current_user(request)
    except Unauthorized:
        return RedirectResponse(f"/connexion?suite={quote(request.url.path)}", status_code=302)
    try:
        microproject = microprojects.get_by_slug(slug)
        if microprojects.role_for(microproject.id, user.id) is None:
            raise NotFound("µprojet introuvable")
        repo = get_repository(slug)
        experiment_id = service.experiment_of_version(repo, version_id)
    except (microprojects.MicroprojectNotFoundError, NotFound):
        return RedirectResponse(f"/microprojets/{slug}", status_code=302)
    query = "" if repo.branches.get(experiment_id) == version_id else f"?version={version_id}"
    return RedirectResponse(f"/microprojets/{slug}/experiences/{experiment_id}{query}", status_code=302)


# Les lectures transverses (statistiques et frise, insights_api.py) vivent sous /api, hors du préfixe
# de ce routeur : include_router le leur ajouterait, leurs routes sont donc reprises telles quelles.
from .insights_api import router as insights_router  # noqa: E402

router.routes.extend(insights_router.routes)
