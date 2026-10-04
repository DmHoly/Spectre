"""Les refs locales d'avant les références : des étiquettes Follow nommées à la main dans chaque
µprojet (« epitaxie-standard »), souvent la même structure de départ dans plusieurs µprojets. Elles
deviennent des références à la première lecture des références (:func:`import_local_refs`, que
chaque fonction de :mod:`.service` appelle d'abord) :

- les étiquettes de tous les µprojets pas encore lus sont regroupées par nom normalisé
  (:func:`.service.normalized_name`), sauf les noms automatiques « ref vX.Y.Z » (et leur suffixe
  « -abc123 »), qui restent de simples repères locaux, et celles d'une structure qui n'est pas un
  procédé dessiné (des images, une campagne : :func:`.service.snapshot_of`) ;
- chaque groupe est une référence (son nom : celui de la plus ancienne étiquette ; une référence
  du même nom existante le reçoit), chaque étiquette une version, dans l'ordre de la date de la
  version étiquetée ; son parent est la dernière version du groupe dont la version étiquetée
  descend (même dépôt), sinon la précédente en date - un **rattachement déduit**
  (``parent_inferred``) ; son numéro suit la règle (:func:`.service.next_number`), une version
  identique à son parent (la même structure étiquetée dans deux µprojets) recevant le mineur
  suivant, ``change_level`` ``none`` ;
- les étiquettes restent en place : aucun objet Follow ni ``refs.json`` n'est écrit.

Chaque µprojet n'est lu qu'**une fois** (``reference_import_scans``) : un µprojet créé ensuite est
marqué lu à la première lecture des références qui suit, et une ref locale nommée plus tard reste
locale - on publie désormais une référence. Une étiquette déjà importée (même µprojet, même nom)
ne l'est jamais deux fois.
"""

from __future__ import annotations

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


@dataclass
class _Candidate:
    microproject: Microproject
    repo: Any
    name: str
    version: follow.Experiment
    experiment_id: str
    snapshot: dict[str, Any]


def _pending(conn) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM microprojects WHERE id NOT IN (SELECT microproject_id FROM reference_import_scans) ORDER BY id"
    ).fetchall()
    return [row["id"] for row in rows]


def _descends(repo: Any, version: follow.Experiment, ancestor_id: str) -> bool:
    """Si ``version`` est ``ancestor_id`` ou en descend (par tous ses parents)."""
    frontier, seen = [version.id], set()
    while frontier:
        current = frontier.pop()
        if current == ancestor_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        try:
            frontier.extend(repo.get(current).parents)
        except (KeyError, follow.FollowError):
            continue
    return False


def _candidates(microproject: Microproject) -> list[_Candidate]:
    repo = get_repository(microproject.slug)
    found = []
    for name, version_id in sorted(repo.tags.items()):
        if AUTOMATIC_REF_NAME_RE.fullmatch(name) or not service.normalized_name(name):
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


def import_local_refs() -> None:
    """Regroupe en références les refs locales des µprojets pas encore lus (voir le module).
    Idempotent : sans µprojet à lire, une requête et rien d'autre."""
    with get_conn() as conn:
        if not _pending(conn):
            return
    with keyed_lock(service.LOCK_NAMESPACE, service.WRITE_LOCK_KEY):
        with get_conn() as conn:
            pending = _pending(conn)
        if not pending:
            return
        scanned = [microprojects.get_by_id(microproject_id) for microproject_id in pending]
        candidates = [candidate for microproject in scanned for candidate in _candidates(microproject)]
        candidates.sort(key=lambda c: (c.version.created_at, c.microproject.id, c.name))
        with get_conn() as conn:
            for candidate in candidates:
                _import(conn, candidate)
            stamp = service.now()
            conn.executemany(
                "INSERT OR IGNORE INTO reference_import_scans (microproject_id, scanned_at) VALUES (?, ?)",
                [(microproject.id, stamp) for microproject in scanned],
            )


def _import(conn, candidate: _Candidate) -> None:
    published_at = candidate.version.created_at.isoformat()
    reference = service.find_by_name(conn, candidate.name)
    if reference is None:
        name = candidate.name.strip()[: service.MAX_NAME_LENGTH]
        reference = service.insert_reference(
            conn, name=name, description="", created_by=candidate.microproject.created_by, created_at=published_at
        )
    versions = service.versions_of(conn, reference.id)
    if any(v.microproject_id == candidate.microproject.id and v.local_tag == candidate.name for v in versions):
        return
    same_line = [
        v for v in versions if v.microproject_id == candidate.microproject.id and _descends(candidate.repo, candidate.version, v.version_id)
    ]
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
