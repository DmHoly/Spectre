"""Les refs locales d'avant les références : des étiquettes Follow nommées à la main dans chaque
µprojet (« epitaxie-standard »), parfois la même structure de départ dans plusieurs µprojets. Seuls
les noms **partagés** deviennent des références (règle décidée le 2026-10-05, :data:`RULE`) - à la
lecture des références qui suit un changement des étiquettes nommées d'un µprojet ou l'arrivée d'un
µprojet pas encore lu (:func:`import_local_refs`, que chaque fonction de :mod:`.service` appelle
d'abord) :

- les étiquettes de **tous** les µprojets sont relues et regroupées par nom normalisé
  (:func:`.service.normalized_name`), sauf les noms automatiques « ref vX.Y.Z » (et leur suffixe
  « -abc123 ») et celles d'une structure qui n'est pas un procédé dessiné (des images, une
  campagne : :func:`.service.snapshot_of`), et celles dont un admin a retiré la référence où elles
  avaient été importées (``dismissed_local_refs``, :func:`.service.delete_reference` : le retrait
  est définitif, elles ne comptent plus pour le partage ; un éditeur peut encore les publier à la
  main) ;
- un nom porté dans **au moins deux µprojets** (:data:`SHARED_BY`) devient une référence et reçoit
  toutes ses étiquettes, de chaque µprojet - lu avant ou non : un nom qui n'était que dans A et qui
  apparaît dans B importe les étiquettes de A et de B à la lecture qui suit ; les autres refs
  nommées restent des repères locaux de leur µprojet (sa page d'évolution les montre), qu'un
  éditeur peut publier à la main (« Publier comme référence ») ;
- la référence d'un nom : celle qui a déjà reçu des étiquettes de ce nom (même renommée), sinon
  celle du même nom, sinon une nouvelle (son nom : celui de la plus ancienne étiquette ; son
  créateur : celui du µprojet de sa première version) ; chaque étiquette une version, dans l'ordre
  de la date de la version étiquetée ; son parent est la dernière version de la référence dont la
  version étiquetée descend (même dépôt), sinon la précédente - un **rattachement déduit**
  (``parent_inferred``) ; son numéro suit la règle (:func:`.service.next_number`), une version
  identique à son parent (la même structure étiquetée dans deux µprojets) recevant le mineur
  suivant, ``change_level`` ``none`` ; une étiquette déjà importée (même µprojet, même nom) ou dont
  la version Follow est déjà une version de la référence (publiée à la main) ne l'est pas deux fois ;
- les étiquettes restent en place : aucun objet Follow ni ``refs.json`` n'est écrit.

Le regroupement ne passe que si l'empreinte des étiquettes nommées d'un µprojet (:func:`_fingerprint`)
a changé depuis sa dernière lecture ou qu'il n'a pas encore été lu (``reference_import_scans``), ou
une fois pour la règle elle-même (``reference_import_rules``) : sur une installation où l'ancienne
règle (chaque ref nommée devenait une référence) a tourné, il retire d'abord les références qu'elle
avait créées depuis un seul µprojet sans que personne n'y touche depuis
(:func:`_retire_unshared_imports`) - leur slug n'est pas réservé, aucune étude n'en est partie -,
puis relit tous les µprojets. Idempotent : sans étiquette changée ni règle à passer, la lecture des
``refs.json`` (dépôts en cache) et une requête, rien d'autre.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import follow

from ...kernel.db import get_conn
from ...kernel.errors import NotFound
from ...kernel.locks import keyed_lock
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from ..microprojects import service as microprojects
from ..microprojects.service import Microproject
from . import service

logger = logging.getLogger(__name__)

# Le nom par défaut d'une ref (experiments.refs : « ref vX.Y.Z », suffixé de 6 caractères de l'id
# quand deux lignées tombent sur le même numéro).
AUTOMATIC_REF_NAME_RE = re.compile(r"^ref v\d+\.\d+\.\d+(?:-[0-9a-z_]{1,6})?$")

# La règle de regroupement en vigueur (reference_import_rules) : seuls les noms portés dans au moins
# SHARED_BY µprojets deviennent des références.
RULE = "shared-names-2026-10-05"
SHARED_BY = 2


@dataclass
class _Candidate:
    microproject: Microproject
    repo: Any
    name: str
    version: follow.Experiment
    experiment_id: str
    snapshot: dict[str, Any]


def _fingerprint(repo) -> str:
    """L'empreinte des étiquettes nommées d'un dépôt (:func:`_named_tags`) : elle change quand une
    ref nommée y est posée, retirée ou déplacée."""
    return hashlib.sha256(json.dumps(_named_tags(repo), ensure_ascii=False).encode("utf-8")).hexdigest()


def _fingerprints(everything: list[Microproject]) -> dict[int, str]:
    return {microproject.id: _fingerprint(get_repository(microproject.slug)) for microproject in everything}


def _needs_run(conn, fingerprints: dict[int, str]) -> bool:
    """Un µprojet pas encore lu ou dont les étiquettes nommées ont changé depuis, ou la règle pas
    encore passée."""
    if not _rule_applied(conn):
        return True
    scanned = {row["microproject_id"]: row["tags_fingerprint"] for row in conn.execute("SELECT * FROM reference_import_scans")}
    return any(scanned.get(microproject_id) != fingerprint for microproject_id, fingerprint in fingerprints.items())


def _rule_applied(conn) -> bool:
    return conn.execute("SELECT 1 FROM reference_import_rules WHERE rule = ?", (RULE,)).fetchone() is not None


def _dismissed(conn) -> set[tuple[int, str]]:
    """Les étiquettes ``(id du µprojet, nom)`` dont un admin a retiré la référence (``dismissed_local_refs``)."""
    return {(row["microproject_id"], row["local_tag"]) for row in conn.execute("SELECT microproject_id, local_tag FROM dismissed_local_refs")}


def _named_tags(repo) -> list[tuple[str, str]]:
    """Les étiquettes nommées à la main d'un dépôt, ``(nom, id de version)`` (ni « ref vX.Y.Z », ni
    un nom sans lettre ni chiffre)."""
    return [
        (name, version_id)
        for name, version_id in sorted(repo.tags.items())
        if not AUTOMATIC_REF_NAME_RE.fullmatch(name) and service.normalized_name(name)
    ]


def candidates_of(microproject: Microproject, names: set[str] | None = None) -> list[_Candidate]:
    """Les refs locales nommées de ``microproject`` qui sont un procédé dessiné - celles dont le nom
    normalisé est dans ``names`` s'il est donné."""
    repo = get_repository(microproject.slug)
    found = []
    for name, version_id in _named_tags(repo):
        if names is not None and service.normalized_name(name) not in names:
            continue
        try:
            version = repo.get(version_id)
        except (KeyError, follow.FollowError):
            continue
        snapshot = service.snapshot_of(repo, version)
        if snapshot is None:
            logger.info("ref locale %r de %s : pas un procédé dessiné, laissée en repère local", name, microproject.slug)
            continue
        try:
            experiment_id = experiments.experiment_of_version(repo, version_id)
        except NotFound:
            experiment_id = version.branch
        found.append(_Candidate(microproject, repo, name, version, experiment_id, snapshot))
    return found


def _shared_candidates(everything: list[Microproject], dismissed: set[tuple[int, str]]) -> list[_Candidate]:
    """Les refs locales de tous les µprojets dont le nom (normalisé) est porté, sur un procédé
    dessiné, dans au moins :data:`SHARED_BY` µprojets - dans l'ordre où les importer (date de la
    version étiquetée). Les étiquettes sont lues d'abord (``refs.json``) : seuls les noms portés dans
    plusieurs µprojets demandent de lire leurs versions. Celles de ``dismissed`` (``(id du µprojet,
    nom)`` : leur référence a été retirée) ne comptent pas."""
    holders: dict[str, set[int]] = {}
    for microproject in everything:
        for name, _version_id in _named_tags(get_repository(microproject.slug)):
            if (microproject.id, name) not in dismissed:
                holders.setdefault(service.normalized_name(name), set()).add(microproject.id)
    wanted = {name for name, ids in holders.items() if len(ids) >= SHARED_BY}
    if not wanted:
        return []
    found = [
        candidate
        for microproject in everything
        for candidate in candidates_of(microproject, wanted)
        if (microproject.id, candidate.name) not in dismissed
    ]
    drawn: dict[str, set[int]] = {}
    for candidate in found:
        drawn.setdefault(service.normalized_name(candidate.name), set()).add(candidate.microproject.id)
    shared = [c for c in found if len(drawn[service.normalized_name(c.name)]) >= SHARED_BY]
    shared.sort(key=lambda c: (c.version.created_at, c.microproject.id, c.name))
    return shared


def _used_slugs(everything: list[Microproject]) -> set[str]:
    """Les slugs de référence que cite une version d'étude, quelle qu'elle soit (``reference_origin``) :
    une référence dont une étude est partie ne se retire pas en silence."""
    used = set()
    for microproject in everything:
        for version in get_repository(microproject.slug):
            origin = experiments.reference_origin_of(version)
            if origin is not None:
                used.add(origin["reference"])
    return used


def _retire_unshared_imports(conn, used: set[str]) -> list[str]:
    """Retire ce que l'ancienne règle avait fait d'une ref locale d'un seul µprojet : une référence
    dont toutes les versions sont des imports (``local_tag``, aucune publication à la main) venus d'un
    seul µprojet, toujours là (une version dont le µprojet a été supprimé - ``microproject_id`` vide -
    garde le seul instantané de sa structure : la référence est gardée), créée par le regroupement
    (sa date : celle de sa première version) et que personne n'a touchée depuis (ni renommée, ni
    décrite : sa date de mise à jour est celle de sa dernière version), dont aucune étude n'est partie (``used``). Son slug n'est pas réservé
    (``retired_reference_slugs`` : aucune étude ne le cite). Renvoie les slugs retirés."""
    retired = []
    for reference in service.all_references(conn):
        versions = service.versions_of(conn, reference.id)
        if not versions or any(v.local_tag is None for v in versions):
            continue
        if any(v.microproject_id is None for v in versions) or len({v.microproject_id for v in versions}) > 1:
            continue
        if reference.slug in used:
            continue
        untouched = (
            reference.created_at == versions[0].published_at
            and reference.updated_at == max(v.published_at for v in versions)
            and not reference.description
        )
        if not untouched:
            continue
        conn.execute("DELETE FROM structure_references WHERE id = ?", (reference.id,))
        retired.append(reference.slug)
    if retired:
        logger.info("références retirées (ref locale d'un seul µprojet, ancienne règle) : %s", ", ".join(retired))
    return retired


def _imported_names(conn) -> dict[str, service.Reference]:
    """La référence qui a déjà reçu des étiquettes de chaque nom (normalisé) - même renommée depuis."""
    rows = conn.execute(
        """SELECT r.*, v.local_tag FROM reference_versions v JOIN structure_references r ON r.id = v.reference_id
           WHERE v.local_tag IS NOT NULL ORDER BY v.id"""
    ).fetchall()
    found: dict[str, service.Reference] = {}
    for row in rows:
        found.setdefault(service.normalized_name(row["local_tag"]), service.reference_from_row(row))
    return found


def _all_microprojects() -> list[Microproject]:
    return sorted(microprojects.list_all(), key=lambda mp: mp.id)


def import_local_refs() -> None:
    """Regroupe en références les refs locales dont le nom est partagé par plusieurs µprojets (voir
    le module), quand les étiquettes nommées d'un µprojet ont changé depuis sa dernière lecture (ou
    qu'il n'a pas encore été lu) ou que la règle n'est pas encore passée."""
    fingerprints = _fingerprints(_all_microprojects())
    with get_conn() as conn:
        if not _needs_run(conn, fingerprints):
            return
    with keyed_lock(service.LOCK_NAMESPACE, service.WRITE_LOCK_KEY):
        # relues sous le verrou : l'empreinte enregistrée est celle des étiquettes regroupées (une ref
        # posée pendant le regroupement le fera repasser à la lecture suivante)
        everything = _all_microprojects()
        fingerprints = _fingerprints(everything)
        with get_conn() as conn:
            if not _needs_run(conn, fingerprints):
                return
            rule_applied = _rule_applied(conn)
            dismissed = _dismissed(conn)
        used = set() if rule_applied else _used_slugs(everything)
        with get_conn() as conn:
            if not rule_applied:
                _retire_unshared_imports(conn, used)
        candidates = _shared_candidates(everything, dismissed)
        with get_conn() as conn:
            imported = _imported_names(conn)
            for candidate in candidates:
                import_candidate(conn, candidate, imported)
            stamp = service.now()
            conn.executemany(
                """INSERT INTO reference_import_scans (microproject_id, scanned_at, tags_fingerprint)
                   SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM microprojects WHERE id = ?)
                   ON CONFLICT (microproject_id) DO UPDATE SET scanned_at = excluded.scanned_at, tags_fingerprint = excluded.tags_fingerprint""",
                [(microproject.id, stamp, fingerprints[microproject.id], microproject.id) for microproject in everything],
            )
            conn.execute("INSERT OR IGNORE INTO reference_import_rules (rule, applied_at) VALUES (?, ?)", (RULE, stamp))


def import_candidate(conn, candidate: _Candidate, imported: dict[str, service.Reference]) -> None:
    """Importe une étiquette dans la référence de son nom (``imported`` : celle qui a déjà reçu ce
    nom, tenue à jour ; sinon celle du même nom, sinon une nouvelle)."""
    key = service.normalized_name(candidate.name)
    published_at = candidate.version.created_at.isoformat()
    reference = imported.get(key) or service.find_by_name(conn, candidate.name)
    if reference is None:
        name = candidate.name.strip()[: service.MAX_NAME_LENGTH]
        reference = service.insert_reference(
            conn, name=name, description="", created_by=candidate.microproject.created_by, created_at=published_at
        )
    imported.setdefault(key, reference)
    versions = service.versions_of(conn, reference.id)
    if any(
        v.microproject_id == candidate.microproject.id and (v.local_tag == candidate.name or v.version_id == candidate.version.id)
        for v in versions
    ):
        return
    same_line = service.published_on_line(versions, candidate.microproject, candidate.repo, candidate.version)
    parent, inferred = (same_line[-1], False) if same_line else ((versions[-1], True) if versions else (None, False))
    level = experiments.structure_change_level(parent.snapshot.get("metadata") if parent else None, candidate.snapshot["metadata"])
    number = service.next_number((v.key for v in versions), parent.key if parent else None, level)
    service.insert_version(
        conn,
        reference,
        number=number,
        parent=parent,
        parent_inferred=inferred,
        microproject=candidate.microproject,
        experiment_id=candidate.experiment_id,
        version_id=candidate.version.id,
        local_tag=candidate.name,
        snapshot=candidate.snapshot,
        change_level=level,
        note="",
        published_by=None,
        published_at=published_at,
    )
