"""Les fiches de plaque : une plaque enregistrée dans Spectre **pour elle-même**, avant toute étude -
le monde d'avant Spectre. L'index des plaques (:mod:`.service`) ne connaît une plaque que par les
études qui la suivent ; une fiche la fait exister sans étude : elle a sa page (``/plaques/{lasermark}``,
sa vie en ligne lue par PRISM), se retrouve dans la recherche, et une étude peut la rattacher plus
tard (carte « Plaques & entités physiques », ou une nouvelle expérience partie d'elle) - c'est là que
sa structure et ses données arrivent.

Le chemin : on cherche des plaques (:func:`lookup`) - dans Spectre d'abord (fiches, études), puis
dans les bases de la ligne, toutes d'un coup (:meth:`TrackingSource.lookup`) - et, pour celles que
la base connaît, on crée leur fiche (:func:`create`). La fiche garde ce que la base en disait ce
jour-là (``summary`` : nom Gozer, lot, produit, dernière étape...) et sa source (``prism``, ``demo``,
ou ``manual`` : créée alors que les bases ne répondaient pas, ou ne la connaissaient pas - une plaque
peut exister avant toute base). Une fiche se supprime par qui l'a créée, ou un administrateur ; une
plaque suivie par une étude garde son index sans elle.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from ...kernel.db import get_conn
from ...kernel.errors import DomainError, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from . import service, tracking
from .service import wafer_key
from .tracking_source import current_source

MAX_LOOKUP = 100
MAX_LASERMARK = 80


def clean_lasermarks(values: Iterable[str]) -> list[str]:
    """Les lasermarks demandés, tels qu'écrits, sans les vides ni les doublons (par clé), dans
    l'ordre - au plus :data:`MAX_LOOKUP` (422 ``too_many_wafers``)."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = " ".join(str(value or "").split())
        key = wafer_key(text)
        if not key or key in seen:
            continue
        if len(text) > MAX_LASERMARK:
            raise InvalidInput(f"Un lasermark de {len(text)} caractères ? « {text[:20]}… »", code="invalid_lasermark")
        seen.add(key)
        out.append(text)
    if len(out) > MAX_LOOKUP:
        raise InvalidInput(f"Au plus {MAX_LOOKUP} plaques à la fois ({len(out)} demandées).", code="too_many_wafers")
    return out


def _payload(row: Any) -> dict[str, Any]:
    return {
        "key": row["wafer_key"],
        "lasermark": row["lasermark"],
        "source": row["source"],
        "summary": json.loads(row["summary"] or "{}"),
        "created_by": row["created_by"],
        "created_by_id": row["created_by_id"],
        "created_at": row["created_at"],
    }


def all_records() -> dict[str, dict[str, Any]]:
    """Toutes les fiches, par clé de plaque."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM wafer_records").fetchall()
    return {row["wafer_key"]: _payload(row) for row in rows}


def get(lasermark: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_records WHERE wafer_key = ?", (wafer_key(lasermark),)).fetchone()
    return _payload(row) if row else None


def _base_lookup(lasermarks: list[str]) -> tuple[dict[str, dict[str, Any] | None], str, str | None]:
    """Ce que la base dit de ces plaques, le nom de la source, et l'erreur si elle n'a pas répondu
    (la recherche et la création n'en sont pas empêchées : Spectre répond quand même)."""
    source = current_source()
    try:
        return source.lookup(lasermarks), source.name, None
    except DomainError as exc:
        return {}, source.name, str(exc)


def lookup(user: User, lasermarks: list[str]) -> dict[str, Any]:
    """Retrouver des plaques, dans Spectre puis dans la base : par lasermark demandé, ``record`` (sa
    fiche, ou ``None``), ``studies`` (combien d'études la suivent, vues par ``user``),
    ``microprojects`` (les leurs), ``base`` (ce que la base en dit, ``None`` si elle ne la connaît
    pas ou n'a pas répondu) ; ``source`` et ``base_error`` disent d'où vient ``base`` et pourquoi il
    manquerait."""
    wanted = clean_lasermarks(lasermarks)
    found = service.occurrences(user, keys=wanted)
    records = all_records()
    summaries, source, error = _base_lookup(wanted)
    items = []
    for lasermark in wanted:
        key = wafer_key(lasermark)
        group = [o for o in found if o.key == key]
        items.append(
            {
                "lasermark": lasermark,
                "key": key,
                "record": records.get(key),
                "studies": len(group),
                "microprojects": service.unique(service.microproject_ref(o.microproject) for o in group),
                "base": summaries.get(key),
            }
        )
    return {"items": items, "source": source, "base_error": error}


def create(user: User, lasermarks: list[str]) -> dict[str, Any]:
    """Les fiches de ces plaques : créées pour celles qui n'en ont pas (avec ce que la base en dit
    aujourd'hui ; source ``manual`` pour une plaque que la base ne connaît pas ou n'a pas pu dire),
    rendues telles quelles pour les autres - ``created`` le dit pour chacune."""
    wanted = clean_lasermarks(lasermarks)
    if not wanted:
        raise InvalidInput("Aucun lasermark.", code="no_lasermark")
    existing = all_records()
    summaries, source, error = _base_lookup([lm for lm in wanted if wafer_key(lm) not in existing])
    now = datetime.now(timezone.utc).isoformat()
    items = []
    with get_conn() as conn:
        for lasermark in wanted:
            key = wafer_key(lasermark)
            if key in existing:
                items.append({**existing[key], "created": False})
                continue
            summary = summaries.get(key)
            conn.execute(
                "INSERT INTO wafer_records (wafer_key, lasermark, source, summary, created_by, created_by_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, lasermark, source if summary else "manual", json.dumps(summary or {}, ensure_ascii=False), user.name, user.id, now),
            )
            items.append(
                {"key": key, "lasermark": lasermark, "source": source if summary else "manual", "summary": summary or {}, "created_by": user.name, "created_by_id": user.id, "created_at": now, "created": True}
            )
    # plaques nouvelles : leur vie en ligne (et le lot JIRA qui en découle) est lue tout de suite
    tracking.prefetch([item["lasermark"] for item in items if item["created"]])
    return {"items": items, "source": source, "base_error": error}


def delete(user: User, lasermark: str) -> None:
    """Supprime la fiche (404 sans fiche ; 403 pour qui ne l'a pas créée et n'est pas
    administrateur). Les études qui suivent la plaque n'en sont pas touchées."""
    record = get(lasermark)
    if record is None:
        raise NotFound(f"Pas de fiche pour la plaque « {lasermark} ».", code="wafer_record_not_found")
    if record["created_by_id"] != user.id and not user.is_admin:
        raise Forbidden("Seul l'auteur de la fiche, ou un administrateur, peut la supprimer.", code="wafer_record_forbidden")
    with get_conn() as conn:
        conn.execute("DELETE FROM wafer_records WHERE wafer_key = ?", (record["key"],))
