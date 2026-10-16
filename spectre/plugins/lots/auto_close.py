"""Un lot se clôt tout seul quand il s'arrête : toutes ses plaques à l'arrêt depuis
:data:`STOPPED_AFTER` (une semaine, tout mouvement compris - étape MES, test, ticket JIRA, épitaxie :
le dernier mouvement que la vie en ligne de chaque plaque connaît). Le lot passe alors « sorti »,
avec pour fin déclarée le jour du dernier mouvement de ses plaques et ``stopped_since`` - on voit
quand il s'est arrêté.

Il ne se clôt pas :

- tant qu'une de ses plaques n'a jamais été lue en ligne (son arrêt est inconnu) ;
- s'il est déclaratif et « en préparation » (pas encore commencé : ses plaques attendent) ;
- si quelqu'un a choisi son statut à la main après le dernier mouvement (``status_set_at``) : rouvrir
  un lot arrêté reste possible, la règle ne le referme pas derrière lui.

Un lot clos ainsi se rouvre de lui-même (« en cours ») dès qu'une de ses plaques bouge de nouveau.

La règle passe (:func:`sweep`) quand on lit les lots, et quand la vie d'une de leurs plaques vient
d'être relue (:func:`tracking.on_tracking_read`).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from ...kernel import plugin_states
from ...kernel.db import get_conn
from ..wafers import tracking
from . import service as lots

STOPPED_AFTER = timedelta(days=7)
_FORMAT = "%Y-%m-%d %H:%M"


def _moment(value: str | None) -> datetime | None:
    try:
        return datetime.strptime((value or "").replace("T", " ")[:16], _FORMAT)
    except ValueError:
        return None


def sweep(lot_ids: Iterable[int] | None = None, *, now: datetime | None = None) -> list[int]:
    """Clôt les lots arrêtés et rouvre ceux qui repartent (tous, ou ``lot_ids``) - les ids changés.
    ``now`` : l'heure locale, celle des mouvements des bases."""
    now = now or datetime.now()
    wanted = None if lot_ids is None else sorted(set(lot_ids))
    if wanted == []:
        return []
    sql = "SELECT * FROM lots WHERE (status IN ('planned', 'wip', 'hold') OR stopped_since IS NOT NULL)"
    params: list[Any] = []
    if wanted is not None:
        sql += f" AND id IN ({','.join('?' * len(wanted))})"
        params = list(wanted)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    candidates = [lots.lot_from_row(row) for row in rows]
    wafers = lots.wafers_of(lot.id for lot in candidates)
    movements = tracking.last_movements({w.key for ws in wafers.values() for w in ws})
    changed = []
    with get_conn() as conn:
        for lot in candidates:
            keys = [w.key for w in wafers.get(lot.id, [])]
            if not keys:
                continue
            moves = [movements.get(key) for key in keys]
            known = [m for m in (_moment(m) for m in moves) if m is not None]
            last = max(known) if known else None
            if lot.stopped_since:  # clos par la règle : repart-il ?
                stopped = _moment(lot.stopped_since)
                if lot.status == "done" and last and stopped and last > stopped:
                    conn.execute("UPDATE lots SET status = 'wip', exited_on = NULL, stopped_since = NULL, updated_at = ? WHERE id = ?", (lots.now_iso(), lot.id))
                    changed.append(lot.id)
                elif lot.status != "done":  # rouvert ou changé à la main entre-temps
                    conn.execute("UPDATE lots SET stopped_since = NULL WHERE id = ?", (lot.id,))
                continue
            if lot.source == "declaratif" and lot.status == "planned":
                continue
            if last is None or len(known) < len(keys) or now - last < STOPPED_AFTER:
                continue
            decided = _moment(lot.status_set_at)
            if decided and decided >= last:  # quelqu'un a choisi après le dernier mouvement
                continue
            conn.execute(
                "UPDATE lots SET status = 'done', exited_on = ?, hold_reason = '', stopped_since = ?, updated_at = ? WHERE id = ?",
                (last.date().isoformat(), last.strftime(_FORMAT), lots.now_iso(), lot.id),
            )
            changed.append(lot.id)
    return changed


def sweep_quietly(lot_ids: Iterable[int] | None = None) -> None:
    """:func:`sweep`, sans laisser une erreur empêcher la lecture des lots."""
    try:
        sweep(lot_ids)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("clôture automatique des lots en échec")


def _after_tracking(key: str, lasermark: str, payload: dict[str, Any]) -> None:
    if plugin_states.is_enabled("lots"):
        sweep([lot.id for lot in lots.list_lots(wafer_keys=[key])])


tracking.on_tracking_read(_after_tracking)
