"""La structure attachée à une plaque elle-même, sans passer par une étude ni un µprojet : une plaque
d'avant Spectre (une fiche de plaque) ou toute plaque qu'on veut décrire vite - « elle a vu la
référence µLED 2.1 », « c'est la structure Quick Test de la bibliothèque ».

Deux sources (déclarées par leurs plugins dans :mod:`spectre.plugins.structures.sources`), lues au moment d'attacher (le dessin est gardé tel qu'il était ce jour-là, comme une
fiche de plaque garde ce que la base en disait) :

- ``reference`` : une version d'une référence (``source_id`` = son slug, ``version`` = son numéro),
  dessinée par le plugin references ;
- ``saved`` : une structure de la bibliothèque des procédés (``source_id`` = son id), simulée par
  StructureForge puis dessinée.

Une étude qui suit la plaque reste prioritaire sur sa page (sa structure est celle qu'elle a vue
dans l'étude) ; la structure attachée est celle qu'on montre sinon. Chacun peut attacher, remplacer
ou retirer la structure d'une plaque - comme créer sa fiche.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput, NotFound
from ..accounts.service import User
from ..structures import sources
from .service import wafer_key

Kind = Literal["reference", "saved"]


def _payload(row: Any) -> dict[str, Any]:
    return {
        "key": row["wafer_key"],
        "lasermark": row["lasermark"],
        "kind": row["kind"],
        "source_id": row["source_id"],
        "version": row["version"],
        "label": row["label"],
        "svg": row["svg"],
        "note": row["note"],
        "attached_by": row["attached_by"],
        "attached_by_id": row["attached_by_id"],
        "attached_at": row["attached_at"],
    }


def get(lasermark: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_structures WHERE wafer_key = ?", (wafer_key(lasermark),)).fetchone()
    return _payload(row) if row else None


def attach(user: User, lasermark: str, *, kind: Kind, source_id: str, version: str | None = None, note: str = "") -> dict[str, Any]:
    """Attache (ou remplace) la structure de la plaque ``lasermark``."""
    key = wafer_key(lasermark)
    if not key:
        raise InvalidInput("Lasermark manquant.", code="no_lasermark")
    source_id = (source_id or "").strip()
    if not source_id:
        raise InvalidInput("Quelle structure ?", code="no_structure")
    found = sources.resolve(kind, user, source_id, (version or "").strip() or None)
    version, label, svg = found.version, found.label, found.svg
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wafer_structures (wafer_key, lasermark, kind, source_id, version, label, svg, note, attached_by, attached_by_id, attached_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wafer_key) DO UPDATE SET lasermark = excluded.lasermark, kind = excluded.kind, source_id = excluded.source_id,
                   version = excluded.version, label = excluded.label, svg = excluded.svg, note = excluded.note,
                   attached_by = excluded.attached_by, attached_by_id = excluded.attached_by_id, attached_at = excluded.attached_at""",
            (key, " ".join(lasermark.split()), kind, source_id, version, label, svg, " ".join((note or "").split())[:300], user.name, user.id, now),
        )
    found = get(key)
    assert found is not None
    return found


def detach(lasermark: str) -> None:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM wafer_structures WHERE wafer_key = ?", (wafer_key(lasermark),))
    if not cursor.rowcount:
        raise NotFound("Aucune structure attachée à cette plaque.", code="wafer_structure_not_found")
