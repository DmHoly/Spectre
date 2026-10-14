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
from datetime import datetime, timedelta, timezone
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import DomainError
from ...kernel.locks import keyed_lock
from . import tracking_model
from .service import wafer_key
from .tracking_source import current_source

logger = logging.getLogger(__name__)

AUTO_REFRESH_AFTER = timedelta(hours=24)
DORMANT_AFTER = timedelta(days=30)
AGING_AFTER = timedelta(days=7)

_MOVEMENT_FORMAT = "%Y-%m-%d %H:%M"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row(key: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_tracking WHERE wafer_key = ?", (key,)).fetchone()
    return dict(row) if row else None


def _save(key: str, lasermark: str, source: str, payload: dict[str, Any], fetched_at: datetime, error: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO wafer_tracking (wafer_key, lasermark, source, fetched_at, last_movement, payload, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(wafer_key) DO UPDATE SET lasermark = excluded.lasermark, source = excluded.source,
                   fetched_at = excluded.fetched_at, last_movement = excluded.last_movement,
                   payload = excluded.payload, error = excluded.error""",
            (key, lasermark, source, fetched_at.isoformat(), payload.get("last_movement"), json.dumps(payload, ensure_ascii=False), error),
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
