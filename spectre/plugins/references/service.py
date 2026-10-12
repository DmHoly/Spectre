"""Les références de structure : un objet **de toute l'application** (pas d'un µprojet), dont les
versions peuvent venir de µprojets différents - un point de départ qu'on réutilise d'un projet à
l'autre et dont on suit l'évolution.

- **Une référence** : un nom (unique, comparé sans casse, ni accents, ni ponctuation :
  :func:`normalized_name`), une description, son créateur. Son ``slug`` est fixé à la création : une
  étude cite la version dont elle part par lui (``reference_origin``, plugin experiments), il ne
  change donc pas quand on la renomme, et celui d'une référence retirée qui avait des versions n'est
  **jamais redonné** (``retired_reference_slugs``) : les études qui en étaient parties ne passent
  pas à une autre référence du même nom.
- **Une version** : un numéro ``MAJEUR.MINEUR`` **calculé** (:func:`next_number`), la version de
  référence dont elle dérive (``parent``), sa source (le µprojet, la piste et la version Follow
  publiées), son auteur, sa date, une note, et un **instantané** de la structure
  (:func:`snapshot_of` : la structure dessinée, le procédé - substrat, étapes, paramètres déclarés
  avec leur unité -, les ids d'étape, les étiquettes de couches et les briques). L'instantané rend
  la version utilisable (rendu, procédé à reprendre, diff) même si l'étude source change de droits
  ou disparaît ; aucun objet Follow n'est écrit.
- **Droits** : tout compte connecté lit les références et en crée une ; publier une version (ce que
  fait le plugin promotion, seul chemin pour choisir une nouvelle référence : :func:`plan_publication`
  puis :func:`record_publication`) demande le rôle ``editor`` sur le µprojet source ; renommer, décrire ou retirer une référence revient à
  son créateur ou à un admin - retirer une référence qui a des versions, à un admin seulement.
- **Masquage** : la source d'une version et les études qui en sont parties ne nomment que leur
  µprojet pour qui n'en est pas membre (la piste, son titre, sa version et le lien restent aux
  membres).
- **Usages** : les études parties d'une version (``reference_origin`` sur la pointe de chaque piste,
  lu dans le dépôt en cache de chaque µprojet) ; une origine qui désigne une référence ou une version
  inconnue n'est comptée nulle part.

Les refs locales d'avant (étiquettes Follow nommées à la main) dont le nom était porté dans au moins
deux µprojets ont été regroupées en références une fois, par la migration
``0005_local_refs_imported_once`` : :mod:`.local_refs`.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import follow

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ...kernel.locks import keyed_lock
from ..accounts.service import User
from ..experiments import service as experiments
from ..experiments.repository import branch_tips, display_status, get_repository
from ..microprojects import service as microprojects
from ..microprojects.service import Microproject
from ..structures import kinds
from ..structures.simulation import (
    BRICKS_METADATA_KEY,
    LAYER_LABELS_METADATA_KEY,
    LAYER_STEPS_METADATA_KEY,
    STEP_IDS_METADATA_KEY,
)

LOCK_NAMESPACE = "references"
WRITE_LOCK_KEY = "write"  # toutes les écritures des références : une à la fois (numéros uniques)
MAX_NAME_LENGTH = 120
MAX_TEXT_LENGTH = 2000
MAX_SLUG_LENGTH = 80  # celle du slug d'une origine (experiments.schemas.ReferenceOrigin)
NUMBER_RE = re.compile(r"^([1-9][0-9]{0,4})\.([0-9]{1,5})$")

# Ce que l'instantané d'une version garde des métadonnées de la version Follow publiée : ce qui décrit
# sa structure dessinée (le procédé, les ids d'étape, les étiquettes de couches et les briques).
SNAPSHOT_METADATA_KEYS = (
    "structureforge_process",
    STEP_IDS_METADATA_KEY,
    LAYER_LABELS_METADATA_KEY,
    LAYER_STEPS_METADATA_KEY,
    BRICKS_METADATA_KEY,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- modèle ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reference:
    id: int
    slug: str
    name: str
    description: str
    created_by: int | None
    created_at: str
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class ReferenceVersion:
    id: int
    reference_id: int
    number_major: int
    number_minor: int
    parent_version_id: int | None
    parent_inferred: bool  # rattachement déduit (une ref locale importée d'un autre dépôt)
    microproject_id: int | None  # None : le µprojet source a été supprimé
    microproject_name: str  # son nom à la publication
    experiment_id: str
    version_id: str
    local_tag: str | None  # la ref locale dont la version a été importée
    snapshot: dict[str, Any]
    change_level: str
    note: str
    published_by: int | None
    published_at: str
    variant: int | None = None  # la variante promue d'une campagne (son index), None sinon

    @property
    def number(self) -> str:
        return f"{self.number_major}.{self.number_minor}"

    @property
    def key(self) -> tuple[int, int]:
        return (self.number_major, self.number_minor)


def reference_from_row(row: sqlite3.Row) -> Reference:
    return Reference(**{name: row[name] for name in Reference.__dataclass_fields__})


def _version_from_row(row: sqlite3.Row) -> ReferenceVersion:
    values = {name: row[name] for name in ReferenceVersion.__dataclass_fields__ if name not in ("snapshot", "parent_inferred", "variant")}
    # variant : absente pendant la migration 0005 (avant 0006_version_variant)
    variant = row["variant"] if "variant" in row.keys() else None
    return ReferenceVersion(**values, parent_inferred=bool(row["parent_inferred"]), snapshot=json.loads(row["snapshot"]), variant=variant)


def normalized_name(name: str) -> str:
    """Le nom tel qu'on le compare (sans casse, ni accents, ni ponctuation) - et le slug qu'il donne :
    « Épitaxie standard » et « epitaxie-standard » sont la même référence."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")


def _folded(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()


def checked_name(name: str) -> str:
    name = (name or "").strip()
    if not name or not normalized_name(name):
        raise InvalidInput("Donnez un nom à la référence (des lettres ou des chiffres).", code="invalid_reference_name")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidInput(f"Le nom d'une référence fait {MAX_NAME_LENGTH} caractères au plus.", code="invalid_reference_name")
    return name


def all_references(conn: sqlite3.Connection) -> list[Reference]:
    return [reference_from_row(row) for row in conn.execute("SELECT * FROM structure_references ORDER BY id")]


def find_by_name(conn: sqlite3.Connection, name: str) -> Reference | None:
    """La référence dont le nom, comparé par :func:`normalized_name`, est ``name``."""
    wanted = normalized_name(name)
    return next((ref for ref in all_references(conn) if normalized_name(ref.name) == wanted), None)


def _unique_slug(conn: sqlite3.Connection, name: str) -> str:
    """Le slug d'une nouvelle référence : son nom normalisé, suffixé (« -2 »...) s'il est pris par une
    référence ou par une référence retirée (jamais redonné) - :data:`MAX_SLUG_LENGTH` caractères au
    plus, suffixe compris, pour qu'une étude puisse la citer."""
    base = normalized_name(name)[:MAX_SLUG_LENGTH].strip("-") or "reference"
    taken = {row["slug"] for row in conn.execute("SELECT slug FROM structure_references UNION SELECT slug FROM retired_reference_slugs")}
    slug, suffix = base, 2
    while slug in taken:
        tail = f"-{suffix}"
        slug = base[: MAX_SLUG_LENGTH - len(tail)].strip("-") + tail
        suffix += 1
    return slug


def insert_reference(conn: sqlite3.Connection, *, name: str, description: str, created_by: int | None, created_at: str) -> Reference:
    """Une nouvelle référence (le nom vérifié et libre : à l'appelant)."""
    cursor = conn.execute(
        "INSERT INTO structure_references (slug, name, description, created_by, created_at, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_unique_slug(conn, name), name, description, created_by, created_at, created_by, created_at),
    )
    return reference_from_row(conn.execute("SELECT * FROM structure_references WHERE id = ?", (cursor.lastrowid,)).fetchone())


def _get(conn: sqlite3.Connection, slug: str) -> Reference:
    row = conn.execute("SELECT * FROM structure_references WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise NotFound(f"Référence « {slug} » introuvable.", code="reference_not_found")
    return reference_from_row(row)


def versions_of(conn: sqlite3.Connection, reference_id: int) -> list[ReferenceVersion]:
    """Les versions d'une référence, dans l'ordre de leur publication (de leur import)."""
    rows = conn.execute("SELECT * FROM reference_versions WHERE reference_id = ? ORDER BY id", (reference_id,))
    return [_version_from_row(row) for row in rows]


def _version(versions: list[ReferenceVersion], number: str) -> ReferenceVersion:
    found = next((v for v in versions if v.number == number), None)
    if found is None:
        raise NotFound(f"Version « {number} » introuvable pour cette référence.", code="reference_version_not_found")
    return found


# -- numérotation ----------------------------------------------------------------------------------


def next_number(existing: Iterable[tuple[int, int]], parent: tuple[int, int] | None, level: str) -> tuple[int, int]:
    """Le numéro d'une nouvelle version, ``existing`` étant ceux déjà pris : la première est 1.0 ; un
    changement majeur (ou une version sans parent) ouvre le majeur suivant **le plus grand pris**
    (un majeur quand 2.0 existe : 3.0) ; tout autre changement - mineur, retouche (étiquettes,
    unité, nom d'étape seuls), ou aucun pour un import - prend le mineur suivant le plus grand pris
    sous le majeur du parent (deux dérivations de 1.0 : 1.1 puis 1.2). Les numéros sont ainsi
    uniques, même entre branches parallèles."""
    taken = list(existing)
    if not taken:
        return (1, 0)
    if parent is None or level in ("initial", "major"):
        return (max(major for major, _minor in taken) + 1, 0)
    return (parent[0], max(minor for major, minor in taken if major == parent[0]) + 1)


# -- filiation -------------------------------------------------------------------------------------


def descends(repo: follow.Repository, version: follow.Experiment, ancestor_id: str) -> bool:
    """Si ``version`` (lue dans ``repo``) est ``ancestor_id`` ou en descend (par tous ses parents)."""
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


def published_on_line(versions: list[ReferenceVersion], microproject: Microproject, repo: follow.Repository, version: follow.Experiment) -> list[ReferenceVersion]:
    """Les ``versions`` d'une référence publiées depuis ``microproject`` dont ``version`` (lue dans
    son dépôt ``repo``) descend - ou qu'elle est -, dans leur ordre de publication."""
    return [v for v in versions if v.microproject_id == microproject.id and descends(repo, version, v.version_id)]


# -- instantané ------------------------------------------------------------------------------------


def variant_labels(version: follow.Experiment) -> list[str]:
    """Le nom de chaque variante d'une campagne (``[]`` hors campagne) : la plaque qui la suit
    (``physical_tracking``), sinon « Variante n », et les valeurs de ses facteurs."""
    if kinds.KINDS.get(version.structure_type) is not kinds.CAMPAIGN:
        return []
    metadata = version.metadata
    labels = metadata.get("campaign_labels") or []
    entries = (version.structure or {}).get("entries") or []
    count = max(len(metadata.get("campaign_factor_values") or []), len(labels), len(entries))
    tracked = [entry.get("sample_id") if isinstance(entry, dict) else None for entry in metadata.get("physical_tracking") or []]
    names = []
    for i in range(count):
        sample = tracked[i] if i < len(tracked) else None
        detail = labels[i] if i < len(labels) else ""
        names.append(" · ".join(part for part in (sample or f"Variante {i + 1}", detail) if part))
    return names


def snapshot_of(repo: follow.Repository, version: follow.Experiment, variant: int | None = None) -> dict[str, Any] | None:
    """L'instantané de la structure de ``version`` (lue dans ``repo``) : la structure dessinée
    (``structure_type``, ``structure``), les métadonnées qui la décrivent
    (:data:`SNAPSHOT_METADATA_KEYS`, les ids d'étape écrits tels qu'on les lit :
    :func:`experiments.step_ids_of`) et le titre de l'étude. Pour une campagne (un split), celui de
    sa variante ``variant`` : sa structure simulée et son procédé (:func:`kinds.variant_process`, les
    valeurs de ses facteurs appliquées) - :class:`InvalidInput` pour une variante qu'elle n'a pas ou
    n'a pas enregistrée. ``None`` pour une structure qui n'est pas un procédé dessiné (des images, une
    étude sans structure, une campagne sans variante choisie) : une référence est un point de départ
    du constructeur."""
    kind = kinds.KINDS.get(version.structure_type)
    if not isinstance(version.metadata.get("structureforge_process"), dict):
        return None
    if kind is kinds.PROCESS and variant is None:
        structure_type, structure, title = version.structure_type, version.structure, version.title
        process = version.metadata["structureforge_process"]
    elif kind is kinds.CAMPAIGN and variant is not None:
        entries = (version.structure or {}).get("entries") or []
        if not 0 <= variant < len(entries):
            raise InvalidInput(f"Cette campagne n'a pas de variante n° {variant + 1}.", code="unknown_variant")
        process = kinds.variant_process(version.metadata, experiments.step_ids_of(repo, version), variant)
        labels = variant_labels(version)
        structure_type, structure = kinds.PROCESS.key, entries[variant]
        title = f"{version.title} · {labels[variant]}" if variant < len(labels) else version.title
    else:
        return None
    metadata = {key: copy.deepcopy(version.metadata[key]) for key in SNAPSHOT_METADATA_KEYS if key in version.metadata}
    metadata["structureforge_process"] = copy.deepcopy(process)
    metadata[STEP_IDS_METADATA_KEY] = experiments.step_ids_of(repo, version)
    return {"structure_type": structure_type, "structure": copy.deepcopy(structure), "metadata": metadata, "title": title}


def snapshot_state(snapshot: dict[str, Any]) -> experiments.StructureState:
    """Ce que le diff (et le comparateur) lit d'un instantané : sa structure, ses métadonnées et
    les ids de ses étapes."""
    metadata = snapshot.get("metadata") or {}
    return experiments.StructureState(snapshot["structure_type"], snapshot["structure"], metadata, list(metadata.get(STEP_IDS_METADATA_KEY) or []))


def insert_version(
    conn: sqlite3.Connection,
    reference: Reference,
    *,
    number: tuple[int, int],
    parent: ReferenceVersion | None,
    parent_inferred: bool,
    microproject: Microproject,
    experiment_id: str,
    version_id: str,
    local_tag: str | None,
    snapshot: dict[str, Any],
    change_level: str,
    note: str,
    published_by: int | None,
    published_at: str,
    variant: int | None = None,
) -> ReferenceVersion:
    """Enregistre une version de ``reference`` (son numéro déjà calculé) et avance la date de
    mise à jour de la référence. ``variant`` : la variante promue d'une campagne (sa colonne n'existe
    qu'après la migration 0006 : la 0005 importe sans elle)."""
    cursor = conn.execute(
        """INSERT INTO reference_versions (reference_id, number_major, number_minor, parent_version_id, parent_inferred,
               microproject_id, microproject_name, experiment_id, version_id, local_tag, snapshot, change_level, note,
               published_by, published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            reference.id,
            number[0],
            number[1],
            parent.id if parent else None,
            1 if parent_inferred else 0,
            microproject.id,
            microproject.name,
            experiment_id,
            version_id,
            local_tag,
            json.dumps(snapshot),
            change_level,
            note,
            published_by,
            published_at,
        ),
    )
    if variant is not None:
        conn.execute("UPDATE reference_versions SET variant = ? WHERE id = ?", (variant, cursor.lastrowid))
    conn.execute(
        "UPDATE structure_references SET updated_at = MAX(updated_at, ?) WHERE id = ?",
        (published_at, reference.id),
    )
    return _version_from_row(conn.execute("SELECT * FROM reference_versions WHERE id = ?", (cursor.lastrowid,)).fetchone())


# -- ce que voit un lecteur ------------------------------------------------------------------------


class _Viewer:
    """Ce qu'un compte voit des µprojets (une lecture pour toutes les références d'une réponse) :
    les µprojets par id, son accès à chacun, et les usages des versions de référence."""

    def __init__(self, user: User) -> None:
        self.user = user
        everything = microprojects.list_all()
        self.microprojects = {mp.id: mp for mp in everything}
        self.access = microprojects.accesses(user, everything)
        self._usages: dict[tuple[str, str], list[tuple[Microproject, follow.Experiment]]] | None = None

    def is_member(self, microproject_id: int | None) -> bool:
        access = self.access.get(microproject_id) if microproject_id is not None else None
        return access is not None and access.role is not None

    def microproject(self, microproject_id: int | None, fallback_name: str) -> dict[str, Any]:
        """Le µprojet ``microproject_id`` : ``{slug, code, name}`` pour un membre, ``{name}`` sinon,
        ``{name, deleted: true}`` s'il n'existe plus (son nom de l'époque)."""
        mp = self.microprojects.get(microproject_id) if microproject_id is not None else None
        if mp is None:
            return {"name": fallback_name, "deleted": True}
        if not self.is_member(mp.id):
            return {"name": mp.name}
        return {"slug": mp.slug, "code": mp.code, "name": mp.name}

    def usages(self) -> dict[tuple[str, str], list[tuple[Microproject, follow.Experiment]]]:
        """Les études parties de chaque version de référence, ``(slug, numéro)`` : la pointe de chaque
        piste qui porte une origine (une lecture du dépôt en cache par µprojet)."""
        if self._usages is None:
            index: dict[tuple[str, str], list[tuple[Microproject, follow.Experiment]]] = {}
            for mp in self.microprojects.values():
                for tip in branch_tips(get_repository(mp.slug)):
                    origin = experiments.reference_origin_of(tip)
                    if origin is not None:
                        index.setdefault((origin["reference"], origin["version"]), []).append((mp, tip))
            for found in index.values():
                found.sort(key=lambda pair: (pair[1].created_at, pair[0].id), reverse=True)
            self._usages = index
        return self._usages

    def usage_payload(self, mp: Microproject, tip: follow.Experiment) -> dict[str, Any]:
        """Une étude partie d'une version : la piste, son titre et son statut pour un membre de son
        µprojet ; le nom du µprojet seul pour les autres."""
        if not self.is_member(mp.id):
            return {"microproject": {"name": mp.name}, "linked": False}
        return {
            "microproject": {"slug": mp.slug, "code": mp.code, "name": mp.name},
            "experiment_id": tip.branch,
            "title": tip.title,
            "status": display_status(tip),
            "updated_at": tip.created_at.isoformat(),
            "linked": True,
        }


def _user_names(conn: sqlite3.Connection, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = sorted({user_id for user_id in ids if user_id is not None})
    if not wanted:
        return {}
    rows = conn.execute(f"SELECT id, name FROM users WHERE id IN ({','.join('?' * len(wanted))})", wanted)
    return {row["id"]: row["name"] for row in rows}


def _person(names: dict[int, str], user_id: int | None) -> dict[str, Any] | None:
    return {"id": user_id, "name": names[user_id]} if user_id is not None and user_id in names else None


def can_manage(user: User, reference: Reference) -> bool:
    """Renommer, décrire, retirer : le créateur de la référence ou un admin."""
    return user.is_admin or (reference.created_by is not None and reference.created_by == user.id)


def _source(viewer: _Viewer, version: ReferenceVersion) -> dict[str, Any]:
    """D'où vient une version : son µprojet (masqué pour qui n'en est pas membre), et pour un membre
    la piste, la version Follow, le titre de l'étude et la ref locale importée."""
    microproject = viewer.microproject(version.microproject_id, version.microproject_name)
    if "slug" not in microproject:
        return {"microproject": microproject, "linked": False}
    return {
        "microproject": microproject,
        "experiment_id": version.experiment_id,
        "version_id": version.version_id,
        "title": version.snapshot.get("title"),
        "variant": version.variant,
        "local_tag": version.local_tag,
        "linked": True,
    }


def _version_payload(
    viewer: _Viewer, reference: Reference, version: ReferenceVersion, by_id: dict[int, ReferenceVersion], names: dict[int, str]
) -> dict[str, Any]:
    parent = by_id.get(version.parent_version_id) if version.parent_version_id is not None else None
    usages = viewer.usages().get((reference.slug, version.number), [])
    return {
        "number": version.number,
        "major": version.number_major,
        "minor": version.number_minor,
        "label": f"{reference.name} {version.number}",
        "change_level": version.change_level,
        "parent": parent.number if parent else None,
        "parent_inferred": version.parent_inferred,
        "imported": version.local_tag is not None,
        "note": version.note,
        "published_by": _person(names, version.published_by),
        "published_at": version.published_at,
        "source": _source(viewer, version),
        "usage_count": len(usages),
        "usages": [viewer.usage_payload(mp, tip) for mp, tip in usages],
    }


def _reference_payload(viewer: _Viewer, reference: Reference, versions: list[ReferenceVersion], names: dict[int, str]) -> dict[str, Any]:
    by_id = {v.id: v for v in versions}
    latest = versions[-1] if versions else None
    latest_payload = None
    if latest is not None:
        full = _version_payload(viewer, reference, latest, by_id, names)
        latest_payload = {key: full[key] for key in ("number", "label", "change_level", "published_by", "published_at", "source", "note")}
    usages = viewer.usages()
    return {
        "slug": reference.slug,
        "name": reference.name,
        "description": reference.description,
        "created_by": _person(names, reference.created_by),
        "created_at": reference.created_at,
        "updated_by": _person(names, reference.updated_by),
        "updated_at": reference.updated_at,
        "latest_version": latest_payload,
        "version_count": len(versions),
        "usage_count": sum(len(usages.get((reference.slug, v.number), [])) for v in versions),
        "can_edit": can_manage(viewer.user, reference),
    }


# -- lectures --------------------------------------------------------------------------------------


def list_references(user: User, q: str = "") -> list[dict[str, Any]]:
    """Toutes les références, de la plus récemment mise à jour (une version publiée la met à jour) à
    la plus ancienne ; ``q`` cherche dans le nom, le slug et la description (sans casse ni accents)."""
    needle = _folded(q.strip())
    viewer = _Viewer(user)
    with get_conn() as conn:
        references = [ref for ref in all_references(conn) if not needle or any(needle in _folded(text) for text in (ref.name, ref.slug, ref.description))]
        versions = {ref.id: versions_of(conn, ref.id) for ref in references}
        names = _user_names(
            conn, [ref.created_by for ref in references] + [ref.updated_by for ref in references] + [v.published_by for vs in versions.values() for v in vs]
        )
    references.sort(key=lambda ref: (ref.updated_at, ref.id), reverse=True)
    return [_reference_payload(viewer, ref, versions[ref.id], names) for ref in references]


def get_reference(user: User, slug: str) -> dict[str, Any]:
    viewer = _Viewer(user)
    with get_conn() as conn:
        reference = _get(conn, slug)
        versions = versions_of(conn, reference.id)
        names = _user_names(conn, [reference.created_by, reference.updated_by] + [v.published_by for v in versions])
    return _reference_payload(viewer, reference, versions, names)


def version_graph(user: User, slug: str) -> dict[str, Any]:
    """``{reference, lanes, nodes, edges}`` : l'évolution d'une référence, comme la page d'évolution
    d'un µprojet - les versions dans l'ordre de leur publication (``nodes``, chacune avec sa
    ``lane``), une arête parent → enfant (``kind`` : ``parent`` dans la même colonne, ``branch``
    pour une branche parallèle ; ``inferred`` : un rattachement déduit à l'import). Une version
    prend la colonne de son parent si elle en est le premier enfant, sinon une nouvelle colonne."""
    viewer = _Viewer(user)
    with get_conn() as conn:
        reference = _get(conn, slug)
        versions = versions_of(conn, reference.id)
        names = _user_names(conn, [reference.created_by, reference.updated_by] + [v.published_by for v in versions])
    by_id = {v.id: v for v in versions}
    lane_of: dict[int, int] = {}
    continued: set[int] = set()
    lanes: list[dict[str, Any]] = []
    nodes, edges = [], []
    for version in versions:
        parent = by_id.get(version.parent_version_id) if version.parent_version_id is not None else None
        if parent is not None and parent.id not in continued:
            lane_of[version.id] = lane_of[parent.id]
        else:
            lane_of[version.id] = len(lanes)
            lanes.append({"index": len(lanes), "start": version.number})
        lanes[lane_of[version.id]]["head"] = version.number
        if parent is not None:
            continued.add(parent.id)
            kind = "parent" if lane_of[parent.id] == lane_of[version.id] else "branch"
            edges.append({"parent": parent.number, "child": version.number, "kind": kind, "inferred": version.parent_inferred})
        nodes.append({**_version_payload(viewer, reference, version, by_id, names), "lane": lane_of[version.id]})
    return {"reference": _reference_payload(viewer, reference, versions, names), "lanes": lanes, "nodes": nodes, "edges": edges}


def read_version(slug: str, number: str | None = None) -> tuple[Reference, ReferenceVersion]:
    """La version ``number`` de la référence ``slug``, la dernière publiée sans numéro (404
    ``reference_not_found``, ``reference_version_not_found`` - une référence sans version aussi) :
    ce que lit le comparateur."""
    with get_conn() as conn:
        reference = _get(conn, slug)
        versions = versions_of(conn, reference.id)
    if number:
        return reference, _version(versions, number)
    if not versions:
        raise NotFound("Cette référence n'a pas encore de version.", code="reference_version_not_found")
    return reference, versions[-1]


def version_numbers(slug: str) -> list[str]:
    """Les numéros des versions de la référence ``slug``, dans l'ordre de leur publication."""
    with get_conn() as conn:
        return [version.number for version in versions_of(conn, _get(conn, slug).id)]


def get_version(user: User, slug: str, number: str) -> dict[str, Any]:
    """Une version : ce que montre son nœud, plus sa structure dessinée par le serveur (étiquettes
    comprises, ``structure_svg``) et son procédé éditable (``process`` : ce que le constructeur
    charge pour lancer une étude depuis cette version - les étapes avec leur id, les étiquettes et
    les briques par positions)."""
    viewer = _Viewer(user)
    with get_conn() as conn:
        reference = _get(conn, slug)
        versions = versions_of(conn, reference.id)
        version = _version(versions, number)
        names = _user_names(conn, [version.published_by])
    by_id = {v.id: v for v in versions}
    snapshot = version.snapshot
    state = snapshot_state(snapshot)
    return {
        **_version_payload(viewer, reference, version, by_id, names),
        "reference": {"slug": reference.slug, "name": reference.name},
        "structure_svg": kinds.render_structure_svg(state.structure_type, state.structure, state.metadata),
        "process": experiments.editable_process_from(state.metadata, state.step_ids),
    }


def versions_published_from(microproject: Microproject) -> list[dict[str, Any]]:
    """Les versions de référence publiées depuis ``microproject`` (le droit de le lire : vérifié par
    l'appelant), les plus récentes d'abord - les badges « R nom 1.1 » de sa page d'évolution."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT v.*, r.slug AS reference_slug, r.name AS reference_name FROM reference_versions v
               JOIN structure_references r ON r.id = v.reference_id
               WHERE v.microproject_id = ? ORDER BY v.published_at DESC, v.id DESC""",
            (microproject.id,),
        ).fetchall()
    return [
        {
            "reference": {"slug": row["reference_slug"], "name": row["reference_name"]},
            "number": f"{row['number_major']}.{row['number_minor']}",
            "label": f"R {row['reference_name']} {row['number_major']}.{row['number_minor']}",
            "experiment_id": row["experiment_id"],
            "version_id": row["version_id"],
            "variant": row["variant"],
            "local_tag": row["local_tag"],
            "change_level": row["change_level"],
            "published_at": row["published_at"],
        }
        for row in rows
    ]


# -- écritures -------------------------------------------------------------------------------------


def taken(name: str) -> Conflict:
    return Conflict(f"Une référence porte déjà le nom « {name} ».", code="reference_name_taken")


def create_reference(user: User, *, name: str, description: str = "") -> Reference:
    """Une nouvelle référence, sans version (on y publie ensuite) : tout compte connecté. 409 pour un
    nom déjà pris (comparé par :func:`normalized_name`)."""
    name = checked_name(name)
    with keyed_lock(LOCK_NAMESPACE, WRITE_LOCK_KEY), get_conn() as conn:
        if find_by_name(conn, name) is not None:
            raise taken(name)
        return insert_reference(conn, name=name, description=(description or "").strip(), created_by=user.id, created_at=now())


def update_reference(user: User, slug: str, changes: dict[str, Any]) -> Reference:
    """Renommer ou décrire une référence (``changes`` : ``name``, ``description``) - son créateur ou
    un admin (403). Le slug ne change pas. Sans effet : rien n'est écrit."""
    with keyed_lock(LOCK_NAMESPACE, WRITE_LOCK_KEY), get_conn() as conn:
        reference = _get(conn, slug)
        if not can_manage(user, reference):
            raise Forbidden("Seuls le créateur de la référence et un administrateur peuvent la modifier.")
        name = reference.name if changes.get("name") is None else checked_name(changes["name"])
        description = reference.description if changes.get("description") is None else changes["description"].strip()
        if (name, description) == (reference.name, reference.description):
            return reference
        other = find_by_name(conn, name)
        if other is not None and other.id != reference.id:
            raise taken(name)
        conn.execute(
            "UPDATE structure_references SET name = ?, description = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (name, description, user.id, now(), reference.id),
        )
        return _get(conn, slug)


def delete_reference(user: User, slug: str) -> None:
    """Retirer une référence : son créateur ou un admin (403) ; une référence qui a des versions, un
    admin seulement (409 ``reference_has_versions`` pour son créateur), ses versions partent avec
    elle - les études qui en sont parties gardent leur origine, lue alors comme inconnue : son slug
    n'est plus jamais redonné (``retired_reference_slugs``). Celui d'une référence sans version
    (aucune étude n'a pu en partir : une version ne se retire pas seule) se libère."""
    with keyed_lock(LOCK_NAMESPACE, WRITE_LOCK_KEY), get_conn() as conn:
        reference = _get(conn, slug)
        if not can_manage(user, reference):
            raise Forbidden("Seuls le créateur de la référence et un administrateur peuvent la retirer.")
        has_versions = conn.execute("SELECT 1 FROM reference_versions WHERE reference_id = ? LIMIT 1", (reference.id,)).fetchone()
        if has_versions and not user.is_admin:
            raise Conflict(
                "Cette référence a des versions : seul un administrateur peut la retirer.", code="reference_has_versions"
            )
        if has_versions:
            stamp = now()
            conn.execute("INSERT OR IGNORE INTO retired_reference_slugs (slug, retired_at) VALUES (?, ?)", (reference.slug, stamp))
        conn.execute("DELETE FROM structure_references WHERE id = ?", (reference.id,))


# -- publier : ce que le plugin promotion planifie, vérifie puis enregistre -----------------------


@dataclass(frozen=True)
class PublicationSource:
    """Ce qu'on publie : une version d'étude (lue dans le dépôt de son µprojet) et, pour une
    campagne, la variante choisie."""

    microproject: Microproject
    repo: follow.Repository
    experiment_id: str  # la piste
    version: follow.Experiment
    variant: int | None

    @property
    def is_campaign(self) -> bool:
        return kinds.KINDS.get(self.version.structure_type) is kinds.CAMPAIGN


def read_source(user: User, *, microproject_slug: str, experiment_id: str, version_id: str | None, variant: int | None) -> PublicationSource:
    """La source d'une publication, que ``user`` peut lire (rôle ``viewer`` : 403 sinon ; publier
    demande ``editor``, ce que vérifie une règle de la promotion) - 422 ``unknown_microproject``,
    404 pour une étude ou une version inconnue."""
    try:
        microproject = microprojects.get_by_slug(microproject_slug)
    except microprojects.MicroprojectNotFoundError as exc:
        raise InvalidInput(f"µprojet « {microproject_slug} » introuvable.", code="unknown_microproject") from exc
    microprojects.check_role(user, microproject, "viewer")
    repo = get_repository(microproject.slug)
    return PublicationSource(microproject, repo, experiment_id, experiments.version_of(repo, experiment_id, version_id), variant)


@dataclass(frozen=True)
class Publication:
    """Une publication planifiée (rien n'est écrit) : l'instantané de la source (``None`` : pas un
    procédé dessiné, ``snapshot_error`` dit pourquoi quand c'est une variante illisible), la
    référence visée (``None`` : une nouvelle référence), ses versions, la version dont la nouvelle
    dériverait (``base``), le changement de structure depuis elle (``level``), le numéro qu'elle
    prendrait et la version de cette référence déjà publiée depuis la même source (``already``)."""

    source: PublicationSource
    snapshot: dict[str, Any] | None
    snapshot_error: InvalidInput | None
    reference: Reference | None
    versions: list[ReferenceVersion]
    base: ReferenceVersion | None
    level: str | None
    number: str | None
    already: ReferenceVersion | None


def _published_from(conn: sqlite3.Connection, microproject: Microproject) -> list[tuple[str, ReferenceVersion]]:
    rows = conn.execute(
        """SELECT v.*, r.slug AS reference_slug FROM reference_versions v JOIN structure_references r ON r.id = v.reference_id
           WHERE v.microproject_id = ? ORDER BY v.published_at DESC, v.id DESC""",
        (microproject.id,),
    ).fetchall()
    return [(row["reference_slug"], _version_from_row(row)) for row in rows]


def suggested_target(conn: sqlite3.Connection, source: PublicationSource) -> dict[str, Any] | None:
    """La référence où publier d'office ``source`` : celle dont part l'étude (``reference_origin``),
    à la suite de la dernière version qui y a été publiée depuis la piste (republier une étude
    partie d'une référence continue sa suite : 1.1 puis 1.2), sinon depuis la version d'origine ;
    sans origine, la dernière référence où a été publiée une version dont elle descend - ``None``
    sinon. ``{reference, parent, why}``."""
    origin = experiments.reference_origin_of(source.version)
    on_line = [
        (slug, v) for slug, v in _published_from(conn, source.microproject) if descends(source.repo, source.version, v.version_id)
    ]
    if origin is not None and find_slug(conn, origin["reference"]) is not None:
        same = next((v for slug, v in on_line if slug == origin["reference"]), None)
        if same is not None:
            return {"reference": origin["reference"], "parent": same.number, "why": f"l'étude en est partie ({origin['version']}) et y a été publiée ({same.number})"}
        return {"reference": origin["reference"], "parent": origin["version"], "why": "l'étude en est partie"}
    if on_line:
        slug, same = on_line[0]
        return {"reference": slug, "parent": same.number, "why": f"une version dont elle descend y a été publiée ({same.number})"}
    return None


def find_slug(conn: sqlite3.Connection, slug: str) -> Reference | None:
    row = conn.execute("SELECT * FROM structure_references WHERE slug = ?", (slug,)).fetchone()
    return reference_from_row(row) if row else None


def plan_publication(conn: sqlite3.Connection, source: PublicationSource, reference: Reference | None, parent: str | None = None) -> Publication:
    """La publication de ``source`` dans ``reference`` (``None`` : une nouvelle référence, dont elle
    serait la 1.0), sans rien écrire. La version dont elle dérive : ``parent`` (un numéro de cette
    référence : 422 ``unknown_parent_version`` sinon) s'il est donné ; sinon la dernière version de
    cette référence publiée depuis ce µprojet dont la source descend (:func:`published_on_line`) ;
    sinon la version dont part la piste (``reference_origin``) ; sinon sa dernière version. Son
    numéro : :func:`next_number` selon le changement de structure depuis elle
    (:func:`experiments.structure_change_level`)."""
    snapshot, error = None, None
    try:
        snapshot = snapshot_of(source.repo, source.version, source.variant)
    except InvalidInput as exc:
        error = exc
    versions = versions_of(conn, reference.id) if reference is not None else []
    base = None
    if parent:
        if not NUMBER_RE.fullmatch(parent) or not any(v.number == parent for v in versions):
            raise InvalidInput(f"Version parente « {parent} » introuvable pour cette référence.", code="unknown_parent_version")
        base = _version(versions, parent)
    elif versions:
        on_line = published_on_line(versions, source.microproject, source.repo, source.version)
        origin = experiments.reference_origin_of(source.version)
        from_origin = None
        if origin is not None and reference is not None and origin["reference"] == reference.slug:
            from_origin = next((v for v in versions if v.number == origin["version"]), None)
        base = (on_line[-1] if on_line else None) or from_origin or versions[-1]
    level = number = None
    if snapshot is not None:
        level = experiments.structure_change_level(base.snapshot.get("metadata") if base else None, snapshot["metadata"])
        if level != "none" or base is None:
            major, minor = next_number((v.key for v in versions), base.key if base else None, level)
            number = f"{major}.{minor}"
    already = next(
        (
            v
            for v in versions
            if v.microproject_id == source.microproject.id and v.version_id == source.version.id and v.variant == source.variant
        ),
        None,
    )
    return Publication(source, snapshot, error, reference, versions, base, level, number, already)


def record_publication(conn: sqlite3.Connection, user: User, plan: Publication, reference: Reference, note: str = "") -> ReferenceVersion:
    """Enregistre ``plan`` (planifiée par :func:`plan_publication`, vérifiée par l'appelant : sous
    :data:`WRITE_LOCK_KEY`, dans la même connexion) comme nouvelle version de ``reference`` - la
    référence planifiée, ou celle que l'appelant vient de créer pour une nouvelle référence."""
    assert plan.snapshot is not None and plan.level is not None
    major, minor = next_number((v.key for v in plan.versions), plan.base.key if plan.base else None, plan.level)
    source = plan.source
    return insert_version(
        conn,
        reference,
        number=(major, minor),
        parent=plan.base,
        parent_inferred=False,
        microproject=source.microproject,
        experiment_id=source.experiment_id,
        version_id=source.version.id,
        local_tag=None,
        snapshot=plan.snapshot,
        change_level=plan.level,
        note=(note or "").strip(),
        published_by=user.id,
        published_at=now(),
        variant=source.variant,
    )
