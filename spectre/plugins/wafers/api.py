"""Plaques (``/api/wafers``) : une seule collection - la recherche par lasermark (``q``) ou par FDL
(``fdl``), les plaques déjà notées dans un µprojet (``microproject``, pour l'autocomplétion de la
fiche) - et le passeport d'une plaque, toutes les études qui la suivent, d'un µprojet à l'autre.
Tout vient de l'index :mod:`.service`, vu selon sa règle de visibilité, et des fiches de plaque
(:mod:`.records`). Les lots qui contiennent une plaque se lisent chez eux : ``GET /api/lots?wafer=``.

Les plaques d'avant Spectre : ``GET /api/wafers/lookup?lasermark=…&lasermark=…`` les cherche dans
Spectre puis dans les bases de la ligne, toutes d'un coup ; ``POST /api/wafer-records`` crée leur
fiche (la plaque existe alors sans étude : sa page, sa vie en ligne, et une étude la rattache plus
tard) ; ``DELETE /api/wafer-records/{wafer_key}`` la retire.

La vie d'une plaque en ligne (``/api/wafers/{wafer_key}/tracking``) : MES, épitaxie et fiche Gozer,
FDL et tests, lus par PRISM (ou la démo) et gardés (:mod:`.tracking`) - relus d'eux-mêmes au plus
toutes les 24 h, plus jamais pour une plaque immobile depuis 30 jours ; ``POST .../tracking/refresh``
relit quoi qu'il arrive.

Les plaques d'une FDL (``/api/fdls/{fdl}``) : celles qu'elle contient réellement, lues dans la source
de :mod:`.fdl_source` (PRISM, la base locale saisie à la main en repli, la démo) - c'est parmi elles
qu'on associe chaque place d'une étude à une vraie plaque.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..accounts.deps import current_user
from ..accounts.service import User
from ..experiments.entities import MAX_TRACKED_ENTITIES
from . import fdl_source, links, notes, records, service, structures, tracking

router = APIRouter(prefix="/api", tags=["wafers"])


@router.get("/wafers")
def list_wafers(
    q: list[str] = Query([], max_length=records.MAX_LOOKUP),
    fdl: str = Query("", max_length=80),
    microproject: str | None = None,
    user: User = Depends(current_user),
) -> list[dict]:
    """Les plaques (``key``, ``lasermark``, ``count``, ``microprojects``, ``latest``, ``fdl``,
    ``locations``, ``record``) dont le lasermark correspond à ``q`` (répété : à l'un des lasermarks
    cherchés), qui portent une FDL correspondant à ``fdl``, suivies dans le µprojet ``microproject``
    (dont il faut être membre) - les filtres se cumulent. Les fiches de plaque y sont (``count`` 0,
    ``latest`` ``None``), sauf dans un µprojet."""
    scope = service.microproject_for(user, microproject) if microproject else None
    queries = [value[:records.MAX_LASERMARK] for value in q]
    return service.wafers(
        service.occurrences(user, microproject=scope),
        q=queries,
        fdl=fdl,
        records=None if scope else records.all_records(),
        line=(line := tracking.line_facts()),
        aliases=links.aliases(),
        lots=service.lot_names_index(line),
    )  # chercher « VA1725 » trouve la plaque dont c'est un run d'épitaxie (le principal ou un autre)


@router.get("/wafers/lookup")
def lookup_wafers(lasermark: list[str] = Query(..., min_length=1, max_length=records.MAX_LOOKUP), user: User = Depends(current_user)) -> dict:
    """Retrouver des plaques, dans Spectre puis dans les bases de la ligne (toutes d'un coup) :
    ``items`` (par lasermark demandé : ``record``, ``studies``, ``microprojects``, ``base`` - ce que
    la base en dit, ``None`` si elle ne la connaît pas), ``source``, ``base_error`` (la base n'a pas
    répondu : les plaques de Spectre sont rendues quand même)."""
    return records.lookup(user, lasermark)


@router.get("/wafers/{wafer_key}")
def get_wafer(wafer_key: str, user: User = Depends(current_user)) -> dict:
    """Le passeport d'une plaque (``wafer_key``, ou son lasermark tel qu'écrit : il est comparé
    sans casse ni séparateurs) et sa fiche de plaque (``record``) - vide (aucune étude, pas de
    fiche) plutôt qu'une 404, la page l'explique."""
    key = service.wafer_key(wafer_key)
    passport = service.passport(wafer_key, service.occurrences(user, keys=[wafer_key]), records.get(wafer_key), tracking.line_facts([key]).get(key))
    passport["links"] = links.chain(wafer_key)
    # « /plaques/VA1725 » : un nom de run d'épitaxie mène aux plaques qui le portent
    passport["run_of"] = service.run_of(wafer_key, tracking.line_facts(), records.all_records())
    passport["structure"] = structures.get(wafer_key)
    passport["notes"] = notes.get(wafer_key)  # son contexte écrit sur sa page
    return passport


class WaferLinkRequest(BaseModel):
    from_lasermark: str = Field(..., max_length=80)
    to_lasermark: str = Field(..., max_length=80)
    note: str = Field("", max_length=links.MAX_NOTE)
    happened_at: str | None = Field(None, max_length=20)


@router.post("/wafer-links", status_code=201)
def create_wafer_link(body: WaferLinkRequest, user: User = Depends(current_user)) -> dict:
    """Déclare qu'une plaque a changé de nom (``from`` est devenue ``to`` : un collage, un report) -
    chercher l'un mène à l'autre. 409 ``wafer_link_exists`` si elles sont déjà reliées."""
    return links.create(user, body.from_lasermark, body.to_lasermark, note=body.note, happened_at=body.happened_at)


@router.delete("/wafer-links/{link_id}", status_code=204)
def delete_wafer_link(link_id: int, user: User = Depends(current_user)) -> None:
    """Retire un lien entre deux noms : un lien déclaré, par son auteur ou un administrateur ; un
    lien vu dans la MES, par un administrateur."""
    links.delete(user, link_id)


class WaferNotesRequest(BaseModel):
    context: str | None = Field(None, max_length=notes.MAX_TEXT)
    hypothesis: str | None = Field(None, max_length=notes.MAX_TEXT)
    learnings: str | None = Field(None, max_length=notes.MAX_TEXT)


@router.put("/wafers/{wafer_key}/notes")
def put_wafer_notes(wafer_key: str, body: WaferNotesRequest, user: User = Depends(current_user)) -> dict | None:
    """Le contexte de la plaque écrit sur sa page : ``context`` (pourquoi elle est là),
    ``hypothesis`` (ce qu'on voulait voir), ``learnings`` (ce qu'on a compris grâce à elle) - les
    champs envoyés seulement ; tous vides, les notes disparaissent (``null``)."""
    return notes.save(user, wafer_key, body.model_dump(exclude_unset=True))


class WaferStructureRequest(BaseModel):
    kind: str = Field(..., pattern="^(reference|saved)$")
    source_id: str = Field(..., min_length=1, max_length=120)
    version: str | None = Field(None, max_length=20)
    note: str = Field("", max_length=300)


@router.put("/wafers/{wafer_key}/structure")
def put_wafer_structure(wafer_key: str, body: WaferStructureRequest, user: User = Depends(current_user)) -> dict:
    """Attache à la plaque une structure, sans étude ni µprojet : une version de référence
    (``kind`` ``reference``, ``source_id`` son slug, ``version`` - la dernière sinon) ou une structure
    de la bibliothèque (``saved``, ``source_id`` son id). Remplace celle qu'elle avait."""
    return structures.attach(user, wafer_key, kind=body.kind, source_id=body.source_id, version=body.version, note=body.note)  # type: ignore[arg-type]


@router.delete("/wafers/{wafer_key}/structure", status_code=204)
def delete_wafer_structure(wafer_key: str, user: User = Depends(current_user)) -> None:
    structures.detach(wafer_key)


class WaferRecordsRequest(BaseModel):
    lasermarks: list[str] = Field(..., min_length=1, max_length=records.MAX_LOOKUP)


@router.post("/wafer-records", status_code=201)
def create_wafer_records(body: WaferRecordsRequest, user: User = Depends(current_user)) -> dict:
    """Les fiches de ces plaques : créées pour celles qui n'en ont pas, avec ce que la base en dit
    aujourd'hui (``source`` ``manual`` quand elle ne la connaît pas, ou n'a pas répondu :
    ``base_error``), rendues telles quelles pour les autres (``created`` le dit)."""
    return records.create(user, body.lasermarks)


@router.delete("/wafer-records/{wafer_key}", status_code=204)
def delete_wafer_record(wafer_key: str, user: User = Depends(current_user)) -> None:
    """Retire la fiche d'une plaque - par son auteur ou un administrateur. Ses études restent."""
    records.delete(user, wafer_key)


@router.get("/wafers/{wafer_key}/tracking")
def get_wafer_tracking(wafer_key: str, user: User = Depends(current_user)) -> dict:
    """La vie de la plaque en ligne (statut MES et étape courante, étapes, épitaxie, FDL et leur
    avancement, tests, fiche Gozer) et ``meta`` : sa fraîcheur (``fetched_at``, ``freshness``,
    ``dormant``, ``auto_refresh``, ``error``). Lue des bases si jamais lue ou plus vieille que 24 h -
    sauf plaque immobile depuis 30 jours - sinon rendue telle que gardée."""
    return tracking.read(wafer_key)


@router.post("/wafers/{wafer_key}/tracking/refresh")
def refresh_wafer_tracking(wafer_key: str, user: User = Depends(current_user)) -> dict:
    """Relit les bases quoi qu'il arrive (le bouton de la page) - même fiche que ``GET``. Une
    relecture en échec garde la fiche précédente et le dit dans ``meta.error``."""
    return tracking.read(wafer_key, refresh=True)


class FdlWafersRequest(BaseModel):
    lasermarks: list[str] = Field(..., max_length=MAX_TRACKED_ENTITIES)


@router.get("/fdls/{fdl}")
def get_fdl(fdl: str, user: User = Depends(current_user)) -> dict:
    """Ce qu'on sait d'une FDL (son numéro tel qu'écrit, normalisé) : ``{fdl, source, editable,
    known, wafers: [{lasermark, slot}]}`` - ``known`` faux quand la source ne la connaît pas encore
    (``editable`` : ses plaques se saisissent alors à la main, ``PUT .../wafers``)."""
    return fdl_source.read(fdl)


@router.put("/fdls/{fdl}/wafers")
def set_fdl_wafers(fdl: str, body: FdlWafersRequest, user: User = Depends(current_user)) -> dict:
    """Les plaques d'une FDL, saisies à la main (dans l'ordre du lot) - seulement quand la source est
    la base locale (409 ``fdl_source_read_only`` sinon : la base de la ligne fait foi)."""
    return fdl_source.write(fdl, body.lasermarks, author=user.name)
