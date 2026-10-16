"""Le contexte d'une plaque, écrit sur sa page : pourquoi elle est là, ce qu'on voulait voir avec elle,
ce qu'on a compris grâce à elle. Une étude d'un µprojet qui la suit le dit déjà (son contexte, son
intention, son hypothèse, sa conclusion - :func:`service._story`) ; ces notes servent quand aucune
étude ne la suit, ou pour ce que la plaque elle-même a appris. Chacun peut les écrire, comme une
fiche de plaque ; qui et quand sont gardés.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput
from ..accounts.service import User
from .service import wafer_key

FIELDS = ("context", "hypothesis", "learnings")
MAX_TEXT = 4000


def _payload(row: Any) -> dict[str, Any]:
    return {
        **{name: row[name] for name in FIELDS},
        "updated_by": row["updated_by"],
        "updated_by_id": row["updated_by_id"],
        "updated_at": row["updated_at"],
    }


def get(lasermark: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_notes WHERE wafer_key = ?", (wafer_key(lasermark),)).fetchone()
    return _payload(row) if row else None


def save(user: User, lasermark: str, values: dict[str, str | None]) -> dict[str, Any] | None:
    """Écrit les notes de la plaque (les champs donnés ; vides, ils s'effacent) - toutes vides, les
    notes disparaissent (``None``)."""
    key = wafer_key(lasermark)
    if not key:
        raise InvalidInput("Lasermark manquant.", code="no_lasermark")
    current = get(key) or {name: None for name in FIELDS}
    merged = {name: (str(values[name]).strip()[:MAX_TEXT] or None) if name in values and values[name] is not None else (None if name in values else current[name]) for name in FIELDS}
    with get_conn() as conn:
        if not any(merged.values()):
            conn.execute("DELETE FROM wafer_notes WHERE wafer_key = ?", (key,))
            return None
        conn.execute(
            """INSERT INTO wafer_notes (wafer_key, lasermark, context, hypothesis, learnings, updated_by, updated_by_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wafer_key) DO UPDATE SET lasermark = excluded.lasermark, context = excluded.context, hypothesis = excluded.hypothesis,
                   learnings = excluded.learnings, updated_by = excluded.updated_by, updated_by_id = excluded.updated_by_id, updated_at = excluded.updated_at""",
            (key, " ".join(lasermark.split()), merged["context"], merged["hypothesis"], merged["learnings"], user.name, user.id, datetime.now(timezone.utc).isoformat()),
        )
    return get(key)
