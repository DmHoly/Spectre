"""La vie d'une plaque en ligne, et quand la relire : la fiche assemblée (:mod:`.tracking_model`)
depuis la source courante (:mod:`.tracking_source`) est gardée dans la table ``wafer_tracking``,
avec sa date de lecture et le dernier mouvement de la plaque, et c'est ici que se décide ce que la
page montre :

- jamais lue, ou rafraîchissement demandé (le bouton) : on lit ;
- la plaque n'a pas bougé depuis :data:`DORMANT_AFTER` (30 jours, toutes sources confondues :
  :func:`tracking_model.last_movement`) : **plus de relecture automatique** - la fiche gardée est
  rendue, et la page le dit ; le bouton relit quand même ;
- sinon, une fiche de plus de :data:`AUTO_REFRESH_AFTER` (24 heures) est relue ; plus jeune, elle
  est rendue telle quelle.

Une relecture qui échoue garde la fiche précédente et rend l'erreur avec elle (``meta.error``) ;
sans fiche précédente, l'erreur est celle de la source (503 configuration, 502 bases). Une plaque à
la fois (:func:`keyed_lock`) : deux onglets qui s'ouvrent ne lisent pas deux fois les bases.

``meta`` dit tout ce qu'il faut pour afficher la fraîcheur : ``fetched_at``, ``age_hours``,
``freshness`` (``fresh`` < 24 h, ``aging`` < 7 j, ``stale`` au-delà), ``last_movement``,
``dormant``, ``auto_refresh`` (faux pour une plaque immobile), ``refreshed`` (cette réponse vient
de lire les bases), ``source`` et ``rules``.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from ...kernel.db import get_conn
from ...kernel.errors import DomainError
from ...kernel.locks import keyed_lock
from . import links, tracking_model
from .service import wafer_key
from .tracking_model import lot_names  # noqa: F401 - lu par les lots JIRA
from .tracking_source import current_source
from .tracking_source import run_prism_hook as run_line_hook  # noqa: F401 - lu par les lots JIRA

logger = logging.getLogger(__name__)

AUTO_REFRESH_AFTER = timedelta(hours=24)
DORMANT_AFTER = timedelta(days=30)
AGING_AFTER = timedelta(days=7)

_MOVEMENT_FORMAT = "%Y-%m-%d %H:%M"

# Ceux qui veulent savoir qu'une plaque vient d'être relue (le plugin lots : le lot JIRA détecté) -
# chacun reçoit (clé, lasermark, fiche assemblée) ; une erreur de l'un n'empêche pas la page.
TrackingListener = Callable[[str, str, dict[str, Any]], None]
_LISTENERS: list[TrackingListener] = []


def on_tracking_read(listener: TrackingListener) -> TrackingListener:
    """Inscrit ``listener`` (une fois) : appelé après chaque lecture des bases d'une plaque."""
    if listener not in _LISTENERS:
        _LISTENERS.append(listener)
    return listener


def _notify(key: str, lasermark: str, payload: dict[str, Any]) -> None:
    try:
        links.record_renames(payload.get("renames") or [])
    except Exception:  # noqa: BLE001 - un lien en moins ne casse pas la page
        logger.exception("suivi de la plaque %s : renommages MES non enregistrés", lasermark)
    for listener in list(_LISTENERS):
        try:
            listener(key, lasermark, payload)
        except Exception:  # noqa: BLE001
            logger.exception("suivi de la plaque %s : l'observateur %s a échoué", lasermark, getattr(listener, "__name__", listener))


def last_movements(keys: Iterable[str]) -> dict[str, str | None]:
    """Par clé de plaque déjà lue en ligne, son dernier mouvement connu ('YYYY-MM-DD HH:MM', toutes
    sources) - une plaque jamais lue n'y est pas."""
    wanted = sorted({wafer_key(k) for k in keys} - {""})
    if not wanted:
        return {}
    with get_conn() as conn:
        rows = conn.execute(f"SELECT wafer_key, last_movement FROM wafer_tracking WHERE wafer_key IN ({','.join('?' * len(wanted))})", wanted).fetchall()
    return {row["wafer_key"]: row["last_movement"] for row in rows}


def line_facts(keys: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """Par clé de plaque déjà lue en ligne : ses FDL (``fdls``, normalisées), son nom de lot JIRA
    (``lot_name``) et ses noms de run d'épitaxie (``run_names``, le principal d'abord) - sans relire
    les bases ni la fiche entière."""
    wanted = None if keys is None else sorted({wafer_key(k) for k in keys} - {""})
    if wanted == []:
        return {}
    sql = "SELECT wafer_key, lasermark, fdls, lot_name, run_names FROM wafer_tracking"
    params: tuple = ()
    if wanted is not None:
        sql += f" WHERE wafer_key IN ({','.join('?' * len(wanted))})"
        params = tuple(wanted)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {
        row["wafer_key"]: {"lasermark": row["lasermark"], "fdls": json.loads(row["fdls"] or "[]"), "lot_name": row["lot_name"], "run_names": json.loads(row["run_names"] or "[]")}
        for row in rows
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row(key: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_tracking WHERE wafer_key = ?", (key,)).fetchone()
    return dict(row) if row else None


def _save(key: str, lasermark: str, source: str, payload: dict[str, Any], fetched_at: datetime, error: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wafer_tracking (wafer_key, lasermark, source, fetched_at, last_movement, payload, error, fdls, lot_name, run_names)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wafer_key) DO UPDATE SET lasermark = excluded.lasermark, source = excluded.source,
                   fetched_at = excluded.fetched_at, last_movement = excluded.last_movement,
                   payload = excluded.payload, error = excluded.error, fdls = excluded.fdls, lot_name = excluded.lot_name,
                   run_names = excluded.run_names""",
            (
                key, lasermark, source, fetched_at.isoformat(), payload.get("last_movement"), json.dumps(payload, ensure_ascii=False), error,
                json.dumps(payload.get("fdl_numbers") or []), payload.get("lot_name"), json.dumps(payload.get("run_names") or []),
            ),
        )


def _mark_error(key: str, error: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE wafer_tracking SET error = ? WHERE wafer_key = ?", (error, key))


def _parse_movement(value: str | None, now: datetime) -> datetime | None:
    """Un mouvement 'YYYY-MM-DD HH:MM' (heure locale de la base) rendu comparable à ``now`` (UTC) -
    à l'heure près, ce qui suffit à une règle en jours."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:16], _MOVEMENT_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_dormant(last_movement: str | None, now: datetime | None = None) -> bool:
    """Une plaque immobile : rien de nouveau depuis :data:`DORMANT_AFTER`. Sans aucun mouvement
    connu (introuvable partout), elle ne l'est pas : on garde une chance de la voir apparaître."""
    moved = _parse_movement(last_movement, now or _utcnow())
    return moved is not None and (now or _utcnow()) - moved > DORMANT_AFTER


def _meta(row: dict[str, Any], now: datetime, *, refreshed: bool) -> dict[str, Any]:
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    age = now - fetched_at
    dormant = is_dormant(row.get("last_movement"), now)
    return {
        "source": row["source"],
        "fetched_at": fetched_at.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "freshness": "fresh" if age < AUTO_REFRESH_AFTER else "aging" if age < AGING_AFTER else "stale",
        "last_movement": row.get("last_movement"),
        "dormant": dormant,
        "auto_refresh": not dormant,
        "refreshed": refreshed,
        "error": row.get("error"),
        "rules": {"auto_refresh_hours": int(AUTO_REFRESH_AFTER.total_seconds() // 3600), "dormant_days": DORMANT_AFTER.days},
    }


def _fetch(key: str, lasermark: str, now: datetime) -> dict[str, Any]:
    source = current_source()
    frames = source.fetch(lasermark)
    payload = tracking_model.build(frames, now=now.astimezone().replace(tzinfo=None))
    _save(key, lasermark, source.name, payload, now, None)
    _notify(key, lasermark, payload)
    return {"wafer_key": key, "lasermark": lasermark, "source": source.name, "fetched_at": now.isoformat(), "last_movement": payload.get("last_movement"), "payload": json.dumps(payload, ensure_ascii=False), "error": None}


def _should_refresh(row: dict[str, Any] | None, now: datetime) -> bool:
    if row is None:
        return True
    if is_dormant(row.get("last_movement"), now):
        return False
    return now - datetime.fromisoformat(row["fetched_at"]) >= AUTO_REFRESH_AFTER


def read(lasermark: str, *, refresh: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """La vie de la plaque ``lasermark`` telle que la page la montre : la fiche (voir
    :func:`tracking_model.build`) et ``meta`` (sa fraîcheur). ``refresh`` relit les bases quoi
    qu'il arrive - le bouton de la page."""
    key = wafer_key(lasermark)
    now = now or _utcnow()
    with keyed_lock("wafer_tracking", key):
        row = _row(key)
        refreshed = False
        if refresh or _should_refresh(row, now):
            try:
                row = _fetch(key, lasermark.strip(), now)
                refreshed = True
            except DomainError as exc:
                if row is None:
                    raise
                logger.warning("suivi de la plaque %s : relecture en échec, fiche du %s gardée (%s)", lasermark, row["fetched_at"], exc)
                _mark_error(key, str(exc))
                row = {**row, "error": str(exc)}
    assert row is not None
    payload = json.loads(row["payload"])
    payload["meta"] = _meta(row, now, refreshed=refreshed)
    return payload


PREFETCH_WORKERS = 6


def prefetch(lasermarks: Iterable[str]) -> int:
    """Première lecture en ligne des plaques qui n'ont encore aucune fiche gardée (un lot ou des
    plaques qu'on vient d'importer : plus besoin d'ouvrir chaque plaque une à une). Les plaques déjà
    gardées sont laissées à leur rythme (24 h) ; un échec n'en empêche pas une autre. Rend le nombre
    de plaques lues."""
    todo = [lm for lm in dict.fromkeys(lasermarks) if _row(wafer_key(lm)) is None]
    if not todo:
        return 0

    def one(lasermark: str) -> bool:
        try:
            read(lasermark)
            return True
        except Exception:  # noqa: BLE001 - la base peut être injoignable : la page de la plaque réessaiera
            logger.warning("suivi de la plaque %s : première lecture en échec", lasermark, exc_info=True)
            return False

    with ThreadPoolExecutor(max_workers=min(PREFETCH_WORKERS, len(todo))) as pool:
        return sum(pool.map(one, todo))
