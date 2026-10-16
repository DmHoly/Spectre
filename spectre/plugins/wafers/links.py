"""Une plaque qui change de nom : d'abord la plaque XX, puis la plaque YY après un collage (ou un
report, un changement de porteur). Les deux noms désignent le même objet physique à deux moments
de sa vie : chercher XX doit mener à YY, et la page de YY doit dire qu'elle s'appelait XX.

Un lien va d'un nom au suivant (``from`` -> ``to``) et vient de deux endroits :

- **la MES** (source ``mes``) : une étape entrée sous un identifiant et sortie sous un autre - lue à
  chaque relecture de la vie en ligne (:func:`record_renames`, appelé par :mod:`.tracking`) ;
- **la main** (source ``manual``) : quand la base ne le sait pas (un collage hors MES), sur la page de
  la plaque (:func:`create`). Un lien manuel se retire par son auteur ou un administrateur ; un lien
  vu dans la MES par un administrateur seulement (la MES le recréerait sinon à la relecture).

Les noms se suivent en chaîne (XX -> YY -> ZZ) : :func:`chain` rend toute la lignée d'une plaque,
d'où qu'on la prenne ; :func:`aliases` donne, par clé de plaque, les autres noms de sa lignée - la
recherche par lasermark s'en sert pour trouver YY quand on tape XX.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from .service import wafer_key

MAX_NOTE = 300


def _payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "from": {"key": row["from_key"], "lasermark": row["from_lasermark"]},
        "to": {"key": row["to_key"], "lasermark": row["to_lasermark"]},
        "source": row["source"],
        "note": row["note"],
        "happened_at": row["happened_at"],
        "created_by": row["created_by"],
        "created_by_id": row["created_by_id"],
        "created_at": row["created_at"],
    }


def all_links() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM wafer_links ORDER BY id").fetchall()
    return [_payload(row) for row in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(lasermark: str) -> str:
    text = " ".join(str(lasermark or "").split())
    if not wafer_key(text):
        raise InvalidInput("Lasermark manquant.", code="no_lasermark")
    if len(text) > 80:
        raise InvalidInput(f"Un lasermark de {len(text)} caractères ? « {text[:20]}… »", code="invalid_lasermark")
    return text


def _connected(links: list[dict[str, Any]], start: str) -> set[str]:
    """Toutes les clés reliées à ``start``, dans un sens ou dans l'autre."""
    seen = {start}
    stack = [start]
    while stack:
        key = stack.pop()
        for link in links:
            for a, b in ((link["from"]["key"], link["to"]["key"]), (link["to"]["key"], link["from"]["key"])):
                if a == key and b not in seen:
                    seen.add(b)
                    stack.append(b)
    return seen


def record_renames(renames: Iterable[dict[str, Any]]) -> int:
    """Les changements de nom vus dans la MES (``{from, to, at}``, :func:`tracking_model.renames`),
    enregistrés s'ils ne le sont pas déjà - combien sont nouveaux."""
    added = 0
    with get_conn() as conn:
        for rename in renames:
            a, b = str(rename.get("from") or "").strip(), str(rename.get("to") or "").strip()
            if not wafer_key(a) or not wafer_key(b) or wafer_key(a) == wafer_key(b):
                continue
            cursor = conn.execute(
                """INSERT OR IGNORE INTO wafer_links (from_key, from_lasermark, to_key, to_lasermark, source, note, happened_at, created_by, created_by_id, created_at)
                   VALUES (?, ?, ?, ?, 'mes', '', ?, 'MES', NULL, ?)""",
                (wafer_key(a), a, wafer_key(b), b, rename.get("at"), _now()),
            )
            added += cursor.rowcount
    return added


def create(user: User, from_lasermark: str, to_lasermark: str, *, note: str = "", happened_at: str | None = None) -> dict[str, Any]:
    """Déclare que la plaque ``from_lasermark`` est devenue ``to_lasermark`` (409 si le lien existe,
    dans un sens ou dans l'autre, ou si les deux noms sont déjà de la même lignée)."""
    a, b = _clean(from_lasermark), _clean(to_lasermark)
    if wafer_key(a) == wafer_key(b):
        raise InvalidInput("Une plaque ne devient pas elle-même.", code="same_wafer")
    note = " ".join((note or "").split())[:MAX_NOTE]
    if wafer_key(b) in _connected(all_links(), wafer_key(a)):
        raise Conflict(f"« {a} » et « {b} » sont déjà reliées.", code="wafer_link_exists")
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO wafer_links (from_key, from_lasermark, to_key, to_lasermark, source, note, happened_at, created_by, created_by_id, created_at)
               VALUES (?, ?, ?, ?, 'manual', ?, ?, ?, ?, ?)""",
            (wafer_key(a), a, wafer_key(b), b, note, (happened_at or "")[:10] or None, user.name, user.id, _now()),
        )
        row = conn.execute("SELECT * FROM wafer_links WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _payload(row)


def delete(user: User, link_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_links WHERE id = ?", (link_id,)).fetchone()
        if row is None:
            raise NotFound("Ce lien entre plaques n'existe pas.", code="wafer_link_not_found")
        mine = row["source"] == "manual" and row["created_by_id"] == user.id
        if not (mine or user.is_admin):
            raise Forbidden(
                "Un lien vu dans la MES ne se retire que par un administrateur." if row["source"] == "mes" else "Seul l'auteur du lien, ou un administrateur, peut le retirer.",
                code="wafer_link_forbidden",
            )
        conn.execute("DELETE FROM wafer_links WHERE id = ?", (link_id,))


def chain(lasermark: str, links: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """La lignée d'une plaque : ``before`` (les noms qu'elle a portés, du plus ancien au plus proche),
    ``after`` (ceux qu'elle a pris ensuite, du plus proche au plus récent), ``current`` (le dernier
    nom de la lignée - celui à suivre aujourd'hui) et les liens eux-mêmes (``links``)."""
    links = all_links() if links is None else links
    key = wafer_key(lasermark)
    group = _connected(links, key)
    mine = [link for link in links if link["from"]["key"] in group]

    def walk(start: str, forward: bool) -> list[dict[str, Any]]:
        out, seen, frontier = [], {start}, [start]
        while frontier:
            nxt = []
            for k in frontier:
                for link in mine:
                    a, b = (link["from"], link["to"]) if forward else (link["to"], link["from"])
                    if a["key"] == k and b["key"] not in seen:
                        seen.add(b["key"])
                        nxt.append(b["key"])
                        out.append({**b, "link_id": link["id"], "source": link["source"], "happened_at": link["happened_at"], "note": link["note"]})
            frontier = nxt
        return out

    before = list(reversed(walk(key, False)))
    after = walk(key, True)
    return {"before": before, "after": after, "current": after[-1] if after else None, "links": mine}


def aliases(links: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    """Par clé de plaque, les autres noms de sa lignée (tels qu'écrits) - pour la recherche."""
    links = all_links() if links is None else links
    names: dict[str, str] = {}
    for link in links:
        names.setdefault(link["from"]["key"], link["from"]["lasermark"])
        names.setdefault(link["to"]["key"], link["to"]["lasermark"])
    out: dict[str, list[str]] = {}
    for key in names:
        out[key] = [names[k] for k in sorted(_connected(links, key) - {key})]
    return out
