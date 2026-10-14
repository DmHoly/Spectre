"""Les commentaires d'étape : un texte libre par étape (son id) d'un µprojet. Un commentaire vide n'existe
pas - l'écrire vide le retire."""

from __future__ import annotations

from dataclasses import dataclass

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput
from ..accounts.service import User
from ..microprojects.service import Microproject
from ..structures.simulation import STEP_ID_RE

MAX_TEXT = 4000
MAX_IDS = 500  # les étapes d'un procédé : bien au-delà de ce qu'on en a vu


@dataclass(frozen=True)
class StepComment:
    step_id: str
    text: str
    updated_at: str  # SQLite « YYYY-MM-DD HH:MM:SS », UTC
    updated_by: str | None  # le nom du compte qui l'a écrit, s'il existe encore


def _checked_id(step_id: str) -> str:
    if not STEP_ID_RE.fullmatch(step_id):
        raise InvalidInput("Identifiant d'étape invalide.", code="invalid_step_id")
    return step_id


def list_comments(microproject: Microproject, step_ids: list[str] | None = None) -> list[StepComment]:
    """Les commentaires du µprojet - ceux des étapes ``step_ids`` quand on les nomme (un id sans
    commentaire est simplement absent du résultat)."""
    if step_ids is not None:
        if len(step_ids) > MAX_IDS:
            raise InvalidInput(f"Au plus {MAX_IDS} étapes à la fois.", code="too_many_steps")
        step_ids = [_checked_id(step_id) for step_id in step_ids]
        if not step_ids:
            return []
    where = f" AND c.step_id IN ({','.join('?' * len(step_ids))})" if step_ids else ""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.step_id, c.text, c.updated_at, u.name AS updated_by FROM step_comments AS c "
            f"LEFT JOIN users AS u ON u.id = c.updated_by WHERE c.microproject_id = ?{where} ORDER BY c.step_id",
            [microproject.id, *(step_ids or [])],
        ).fetchall()
    return [StepComment(row["step_id"], row["text"], row["updated_at"], row["updated_by"]) for row in rows]


def set_comment(microproject: Microproject, user: User, step_id: str, text: str) -> StepComment | None:
    """Écrit le commentaire de l'étape (remplace le précédent) ; ``None`` quand le texte est vide : le
    commentaire est alors retiré."""
    step_id = _checked_id(step_id)
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise InvalidInput(f"Un commentaire fait {MAX_TEXT} caractères au plus.", code="comment_too_long")
    with get_conn() as conn:
        if not text:
            conn.execute("DELETE FROM step_comments WHERE microproject_id = ? AND step_id = ?", (microproject.id, step_id))
            return None
        conn.execute(
            "INSERT INTO step_comments (microproject_id, step_id, text, updated_by, updated_at) VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT (microproject_id, step_id) DO UPDATE SET text = excluded.text, updated_by = excluded.updated_by, updated_at = excluded.updated_at",
            (microproject.id, step_id, text, user.id),
        )
    return list_comments(microproject, [step_id])[0]
