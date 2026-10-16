"""Un lot se clôt tout seul de deux façons, et passe alors « sorti » (``stopped_reason`` dit laquelle) :

- ``fdl`` : **toutes ses FDL sont closes** - celles de ses plaques lues en ligne (ticket JIRA clos, voir
  :func:`..wafers.tracking_model.fdl_closures`) ; fin déclarée = le jour de la dernière clôture ;
- ``idle`` : toutes ses plaques à l'arrêt depuis :data:`STOPPED_AFTER` (une semaine, tout mouvement
  compris - étape MES, test, ticket JIRA, épitaxie : le dernier mouvement que la vie en ligne de
  chaque plaque connaît) ; fin déclarée = le jour du dernier mouvement.

``stopped_since`` garde le moment (clôture de la dernière FDL, ou dernier mouvement) - on voit
quand il s'est arrêté. La règle des FDL passe avant celle de l'arrêt.

Il ne se clôt pas :

- tant qu'une de ses plaques n'a jamais été lue en ligne (son arrêt, ses FDL sont inconnus) ;
- par la règle des FDL, tant qu'aucune de ses plaques n'a de FDL, ou qu'une seule est encore ouverte ;
- s'il est déclaratif et « en préparation » (pas encore commencé : ses plaques attendent) ;
- si quelqu'un a choisi son statut à la main après le dernier mouvement (``status_set_at``) : rouvrir
  un lot arrêté reste possible, la règle ne le referme pas derrière lui.

Un lot clos ainsi se rouvre de lui-même (« en cours ») : celui des FDL dès qu'une FDL s'ouvre (ou qu'une
plaque nouvelle n'a pas encore été lue), celui de l'arrêt dès qu'une de ses plaques bouge de nouveau
(sauf si toutes ses FDL sont closes).

La règle passe (:func:`sweep`) quand on lit les lots, et quand la vie d'une de leurs plaques vient
d'être relue (:func:`tracking.on_tracking_read`).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from ...kernel import plugin_states
from ...kernel.db import get_conn
from ..wafers import tracking
from ..wafers.service import wafer_key
from . import service as lots

STOPPED_AFTER = timedelta(days=7)
_FORMAT = "%Y-%m-%d %H:%M"


def _moment(value: str | None) -> datetime | None:
    try:
        return datetime.strptime((value or "").replace("T", " ")[:16], _FORMAT)
    except ValueError:
        return None


def fdl_end(keys: list[str], closures: dict[str, dict[str, Any]], fallback: datetime | None) -> datetime | None:
    """Quand la dernière FDL du lot s'est close - ou None si le lot n'est pas fini : une plaque jamais
    lue en ligne, aucune FDL, ou une FDL encore ouverte. ``fallback`` : le jour à prendre si aucune
    clôture ne porte de date."""
    facts = [closures.get(wafer_key(key)) for key in keys]
    if any(fact is None for fact in facts):
        return None
    states = [state for fact in facts for state in (fact or {}).values()]
    if not states or not all(state.get("closed") for state in states):
        return None
    dates = [d for d in (_moment(state.get("at")) for state in states) if d is not None]
    return max(dates) if dates else fallback


def _close(conn, lot: lots.Lot, end: datetime, reason: str) -> None:
    conn.execute(
        "UPDATE lots SET status = 'done', exited_on = ?, hold_reason = '', stopped_since = ?, stopped_reason = ?, updated_at = ? WHERE id = ?",
        (end.date().isoformat(), end.strftime(_FORMAT), reason, lots.now_iso(), lot.id),
    )


def _reopen(conn, lot: lots.Lot) -> None:
    conn.execute(
        "UPDATE lots SET status = 'wip', exited_on = NULL, stopped_since = NULL, stopped_reason = NULL, updated_at = ? WHERE id = ?",
        (lots.now_iso(), lot.id),
    )


def sweep(lot_ids: Iterable[int] | None = None, *, now: datetime | None = None) -> list[int]:
    """Clôt les lots finis ou arrêtés et rouvre ceux qui repartent (tous, ou ``lot_ids``) - les ids
    changés. ``now`` : l'heure locale, celle des mouvements des bases."""
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
    all_keys = {w.key for ws in wafers.values() for w in ws}
    movements = tracking.last_movements(all_keys)
    closures = tracking.fdl_closures(all_keys)
    changed = []
    with get_conn() as conn:
        for lot in candidates:
            keys = [w.key for w in wafers.get(lot.id, [])]
            if not keys:
                continue
            moves = [movements.get(key) for key in keys]
            known = [m for m in (_moment(m) for m in moves) if m is not None]
            last = max(known) if known else None
            finished = fdl_end(keys, closures, last or now)
            if lot.stopped_since:  # clos par la règle : repart-il ?
                stopped = _moment(lot.stopped_since)
                if lot.status != "done":  # rouvert ou changé à la main entre-temps
                    conn.execute("UPDATE lots SET stopped_since = NULL, stopped_reason = NULL WHERE id = ?", (lot.id,))
                elif lot.stopped_reason == "fdl":
                    if finished is None:  # une FDL s'ouvre, une plaque arrive : le lot n'est plus fini
                        _reopen(conn, lot)
                        changed.append(lot.id)
                elif finished is None and last and stopped and last > stopped:
                    _reopen(conn, lot)
                    changed.append(lot.id)
                continue
            if lot.source == "declaratif" and lot.status == "planned":
                continue
            if finished is not None:
                end, reason = finished, "fdl"
            elif last is None or len(known) < len(keys) or now - last < STOPPED_AFTER:
                continue
            else:
                end, reason = last, "idle"
            decided = _moment(lot.status_set_at)
            if decided and decided >= end:  # quelqu'un a choisi après la fin
                continue
            _close(conn, lot, end, reason)
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
