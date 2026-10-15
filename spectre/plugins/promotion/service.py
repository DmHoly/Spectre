"""Promouvoir une structure comme référence : le seul chemin pour choisir une nouvelle référence (ou
une nouvelle version d'une référence), depuis n'importe quelle étude - une étude simple, une
variante d'un split, une version passée.

- :func:`preview` : ce que donnerait la promotion, sans rien écrire - la source (et les variantes
  d'un split), la référence proposée, la version dont elle dériverait, le numéro qu'elle prendrait,
  et le verdict de chaque règle (:mod:`.rules`).
- :func:`promote` : la même chose sous le verrou des références, puis, si aucune règle ne bloque, la
  nouvelle référence (si on en nomme une), sa version (:func:`references.record_publication`) et
  l'entrée du journal - dans une seule transaction ; puis, si on l'a demandé (``follow``), l'étude
  (ou toute sa branche) suit désormais cette version (:func:`experiments.set_reference_followed`).
- :func:`journal` : les promotions, les plus récentes d'abord, masquées comme les références (la
  source ne nomme que son µprojet pour qui n'en est pas membre)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput, NotFound
from ...kernel.locks import keyed_lock
from ..accounts.service import User
from ..experiments import service as experiments
from ..experiments.repository import display_status
from ..microprojects import service as microprojects
from ..process_library import service as library
from ..process_library.schemas import brick_payload
from ..process_library.tech_bricks import BrickReference
from ..references import service as references
from ..structures import kinds
from . import brick_rules, rules
from .schemas import BrickPromotionRequest, PromotionRequest

LEVEL_TEXT = {"initial": "première version", "major": "changement majeur", "minor": "changement mineur", "patch": "retouche", "none": "sans changement"}


def _target(conn: sqlite3.Connection, body: PromotionRequest, suggestion: dict[str, Any] | None) -> tuple[references.Reference | None, str | None, str]:
    """La référence visée (``None`` : une nouvelle), le nom et la description d'une nouvelle."""
    if body.new_reference is not None:
        return None, body.new_reference.name, body.new_reference.description
    if body.reference:
        found = references.find_slug(conn, body.reference)
        if found is None:
            raise NotFound(f"Référence « {body.reference} » introuvable.", code="reference_not_found")
        return found, None, ""
    if suggestion is not None:
        return references.find_slug(conn, suggestion["reference"]), None, ""
    return None, "", ""


def _candidate(conn: sqlite3.Connection, user: User, body: PromotionRequest, source: references.PublicationSource) -> tuple[rules.Candidate, dict[str, Any] | None, str]:
    suggestion = references.suggested_target(conn, source)
    reference, new_name, description = _target(conn, body, suggestion)
    parent = body.parent if reference is not None else None
    publication = references.plan_publication(conn, source, reference, parent)
    taken = False
    if reference is None and (new_name or "").strip():
        try:
            taken = references.find_by_name(conn, references.checked_name(new_name)) is not None
        except InvalidInput:
            taken = False
    return rules.Candidate(user, publication, new_name, taken, body.note), suggestion, description


def _source(user: User, body: PromotionRequest) -> references.PublicationSource:
    return references.read_source(
        user, microproject_slug=body.microproject, experiment_id=body.experiment_id, version_id=body.version_id, variant=body.variant
    )


def _followed_payload(conn: sqlite3.Connection, version: Any) -> dict[str, Any] | None:
    followed = experiments.reference_followed_of(version)
    if followed is None:
        return None
    found = references.find_slug(conn, followed["reference"])
    return {**followed, "name": found.name if found else followed["reference"], "is_origin": followed == experiments.reference_origin_of(version)}


def preview(user: User, body: PromotionRequest) -> dict[str, Any]:
    """Ce que donnerait la promotion de ``body`` (rien n'est écrit) : ``{source, suggestion, target,
    parents, base, level, level_text, number, rules, can_promote}``."""
    source = _source(user, body)
    with get_conn() as conn:
        candidate, suggestion, _ = _candidate(conn, user, body, source)
        if suggestion is not None:
            found = references.find_slug(conn, suggestion["reference"])
            suggestion = {**suggestion, "name": found.name if found else suggestion["reference"]}
        followed_payload = _followed_payload(conn, source.version)
    results = rules.evaluate(candidate)
    publication = candidate.publication
    version = source.version
    snapshot = publication.snapshot
    svg = None
    if snapshot is not None:
        svg = kinds.render_structure_svg(snapshot["structure_type"], snapshot["structure"], snapshot["metadata"])
    reference = publication.reference
    return {
        "source": {
            "microproject": {"slug": source.microproject.slug, "name": source.microproject.name},
            "experiment_id": source.experiment_id,
            "version_id": version.id,
            "title": version.title,
            "status": display_status(version),
            "decision": version.conclusion.decision,
            "structure_kind": kinds.structure_kind_name(version.structure_type),
            "variants": [{"index": i, "label": label} for i, label in enumerate(references.variant_labels(version))],
            "variant": source.variant,
            "structure_svg": svg,
            # la version de référence que l'étude suit aujourd'hui ({reference, version, name,
            # is_origin} : son nom, et si c'est encore celle dont elle est partie) - None sans aucune
            "reference_followed": followed_payload,
        },
        "suggestion": suggestion,
        "target": {"reference": {"slug": reference.slug, "name": reference.name} if reference else None, "new_name": candidate.new_name},
        "parents": [
            {"number": v.number, "change_level": v.change_level, "published_at": v.published_at} for v in reversed(publication.versions)
        ],
        "base": publication.base.number if publication.base else None,
        "level": publication.level,
        "level_text": LEVEL_TEXT.get(publication.level or "", ""),
        "number": publication.number,
        "rules": rules.public(results),
        "can_promote": rules.first_block(results) is None,
    }


def promote(user: User, body: PromotionRequest) -> tuple[str, str]:
    """Promouvoir ``body`` : refusée avec l'erreur de la première règle qui bloque ; sinon la
    nouvelle référence (si on en nomme une), sa version et l'entrée du journal ; puis, avec
    ``follow``, l'étude (ou sa branche) suit cette version. Renvoie ``(slug de la référence, numéro
    de la version)``."""
    source = _source(user, body)
    with keyed_lock(references.LOCK_NAMESPACE, references.WRITE_LOCK_KEY), get_conn() as conn:
        candidate, _, description = _candidate(conn, user, body, source)
        results = rules.evaluate(candidate)
        blocked = rules.first_block(results)
        if blocked is not None:
            raise blocked.as_error()
        publication = candidate.publication
        reference = publication.reference
        created = reference is None
        if created:
            reference = references.insert_reference(
                conn, name=references.checked_name(candidate.new_name or ""), description=(description or "").strip(), created_by=user.id, created_at=references.now()
            )
        version = references.record_publication(conn, user, publication, reference, body.note)
        conn.execute(
            """INSERT INTO promotions (reference_id, reference_version_id, reference_slug, reference_name, number, created_reference,
                   microproject_id, microproject_name, experiment_id, version_id, variant, study_title, note, verdicts,
                   promoted_by, promoted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reference.id,
                version.id,
                reference.slug,
                reference.name,
                version.number,
                1 if created else 0,
                source.microproject.id,
                source.microproject.name,
                source.experiment_id,
                source.version.id,
                source.variant,
                (publication.snapshot or {}).get("title") or source.version.title,
                version.note,
                json.dumps(rules.public(results)),
                user.id,
                version.published_at,
            ),
        )
    if body.follow is not None:
        experiments.set_reference_followed(
            source.microproject.slug,
            source.experiment_id,
            {"reference": reference.slug, "version": version.number},
            scope=body.follow,
            author=user.name,
            expected_version=None,
        )
    return reference.slug, version.number


def journal(user: User, *, microproject: str | None = None, experiment_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Les promotions, les plus récentes d'abord (``microproject`` / ``experiment_id`` : celles de ce
    µprojet, de cette piste). La source ne nomme que son µprojet pour qui n'en est pas membre."""
    where, args = [], []
    if microproject:
        found = microprojects.get_by_slug(microproject)
        where.append("p.microproject_id = ?")
        args.append(found.id)
        if experiment_id:
            where.append("p.experiment_id = ?")
            args.append(experiment_id)
    sql = (
        "SELECT p.*, u.name AS promoted_by_name, m.slug AS microproject_slug FROM promotions p"
        " LEFT JOIN users u ON u.id = p.promoted_by LEFT JOIN microprojects m ON m.id = p.microproject_id"
        + (f" WHERE {' AND '.join(where)}" if where else "")
        + " ORDER BY p.promoted_at DESC, p.id DESC LIMIT ?"
    )
    with get_conn() as conn:
        rows = conn.execute(sql, (*args, limit)).fetchall()
    by_slug = {m.slug: m for m in microprojects.list_all()}
    readable = {
        m_id for m_id, access in microprojects.accesses(user, [by_slug[row["microproject_slug"]] for row in rows if row["microproject_slug"] in by_slug]).items() if access.role
    }
    entries = []
    for row in rows:
        member = row["microproject_id"] in readable
        verdicts = json.loads(row["verdicts"] or "[]")
        source: dict[str, Any] = {"microproject": {"name": row["microproject_name"]}, "linked": False}
        if member:
            source = {
                "microproject": {"slug": row["microproject_slug"], "name": row["microproject_name"]},
                "experiment_id": row["experiment_id"],
                "version_id": row["version_id"],
                "variant": row["variant"],
                "title": row["study_title"],
                "linked": True,
            }
        entries.append(
            {
                "reference": {"slug": row["reference_slug"], "name": row["reference_name"], "exists": row["reference_id"] is not None},
                "number": row["number"],
                "created_reference": bool(row["created_reference"]),
                "source": source,
                "note": row["note"],
                "warnings": [v for v in verdicts if v.get("level") == "warn"],
                "promoted_by": row["promoted_by_name"],
                "promoted_at": row["promoted_at"],
            }
        )
    return entries


# -- les briques de référence ----------------------------------------------------------------------


def _brick_candidate(user: User, body: BrickPromotionRequest) -> brick_rules.BrickCandidate:
    entry = library.get_item(library.TECH_BRICKS, user, body.brick_id)
    folded = entry.item.name.strip().casefold()
    taken = any(
        other.item.id != entry.item.id and other.item.name.strip().casefold() == folded
        for other in library.list_items(library.TECH_BRICKS, user, scope="shared")
    )
    return brick_rules.BrickCandidate(user, entry, body.note, taken)


def preview_brick(user: User, body: BrickPromotionRequest) -> dict[str, Any]:
    """Ce que donnerait la promotion de la brique (rien n'est écrit) : ``{brick, rules, can_promote}``."""
    candidate = _brick_candidate(user, body)
    results = brick_rules.evaluate(candidate)
    return {"brick": brick_payload(candidate.entry, user, detail=False), "rules": rules.public(results), "can_promote": rules.first_block(results) is None}


def promote_brick(user: User, body: BrickPromotionRequest) -> dict[str, Any]:
    """Promouvoir la brique comme brique de référence : refusée avec l'erreur de la première règle
    qui bloque ; sinon la brique, partagée, porte sa référence (qui, quand, pourquoi) - c'est son
    journal. Renvoie la brique."""
    candidate = _brick_candidate(user, body)
    results = brick_rules.evaluate(candidate)
    blocked = rules.first_block(results)
    if blocked is not None:
        raise blocked.as_error()
    reference = BrickReference(promoted_by=user.id, promoted_at=references.now(), note=body.note.strip())
    return brick_payload(library.set_brick_reference(user, body.brick_id, reference), user, detail=True)


def editable_microprojects(user: User) -> list[dict[str, Any]]:
    """Les µprojets où ``user`` peut promouvoir (éditeur), par nom - le premier choix du formulaire."""
    everything = microprojects.list_all()
    access = microprojects.accesses(user, everything)
    return sorted(
        ({"slug": m.slug, "name": m.name} for m in everything if access[m.id].at_least("editor")), key=lambda m: m["name"].lower()
    )
