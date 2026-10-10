"""L'enregistrement de l'utilisation : l'observateur de requêtes du plugin (``Plugin.observe``).

Seules les requêtes d'un compte connecté comptent (ni la page de connexion, ni une session
expirée), et pas celles du plugin usage lui-même : regarder le tableau de bord ne le gonfle pas.
Chaque requête ajoute 1 à un compteur en mémoire - le compte, l'heure, le plugin et le gabarit de la
route - et les compteurs rejoignent la table ``usage_counts`` au plus toutes les
``FLUSH_SECONDS`` (et avant toute lecture du rapport : :func:`flush`). Rien de la requête n'est
gardé au-delà : ni chemin réel, ni paramètre, ni corps.

Le compte d'une requête est celui de son cookie de session, lu dans ``accounts`` et gardé en
mémoire ``SESSION_CACHE_SECONDS`` : une page vue ne coûte pas une requête SQL de plus.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from ...kernel.db import get_conn
from ...kernel.errors import DomainError
from ...kernel.plugin import RequestTrace
from ..accounts import service as accounts
from ..accounts.security import SESSION_COOKIE

PLUGIN_NAME = "usage"
FLUSH_SECONDS = 15.0
SESSION_CACHE_SECONDS = 60.0
_SESSION_CACHE_MAX = 2000

_Key = tuple[str, int, int, str, str, str, str]  # day, hour, user_id, plugin, kind, method, route


@dataclass
class _Counter:
    hits: int = 0
    client_errors: int = 0
    server_errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0


_lock = threading.Lock()
_pending: dict[_Key, _Counter] = {}
_last_flush = time.monotonic()
_sessions: dict[str, tuple[int | None, float]] = {}


def now() -> datetime:
    """L'heure locale du serveur (remplacée par les tests)."""
    return datetime.now()


def _user_id(token: str | None) -> int | None:
    if not token:
        return None
    clock = time.monotonic()
    cached = _sessions.get(token)
    if cached is not None and cached[1] > clock:
        return cached[0]
    try:
        user_id: int | None = accounts.session(token)[0].id
    except DomainError:
        user_id = None
    if len(_sessions) >= _SESSION_CACHE_MAX:
        _sessions.clear()
    _sessions[token] = (user_id, clock + SESSION_CACHE_SECONDS)
    return user_id


def observe(trace: RequestTrace) -> None:
    """Compte une requête servie (l'observateur du plugin usage)."""
    if trace.plugin == PLUGIN_NAME:
        return
    user_id = _user_id(trace.cookies.get(SESSION_COOKIE))
    if user_id is None:
        return
    at = now()
    key: _Key = (at.strftime("%Y-%m-%d"), at.hour, user_id, trace.plugin, trace.kind, trace.method, trace.route)
    with _lock:
        counter = _pending.setdefault(key, _Counter())
        counter.hits += 1
        counter.client_errors += 400 <= trace.status < 500
        counter.server_errors += trace.status >= 500
        counter.total_ms += trace.duration_ms
        counter.max_ms = max(counter.max_ms, trace.duration_ms)
        due = time.monotonic() - _last_flush >= FLUSH_SECONDS
    if due:
        flush()


def flush() -> None:
    """Écrit les compteurs en mémoire dans ``usage_counts`` (une transaction)."""
    global _last_flush
    with _lock:
        batch = list(_pending.items())
        _pending.clear()
        _last_flush = time.monotonic()
    if not batch:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO usage_counts (day, hour, user_id, plugin, kind, method, route, hits, client_errors, server_errors, total_ms, max_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (day, hour, user_id, plugin, kind, method, route) DO UPDATE SET
                hits = hits + excluded.hits,
                client_errors = client_errors + excluded.client_errors,
                server_errors = server_errors + excluded.server_errors,
                total_ms = total_ms + excluded.total_ms,
                max_ms = MAX(max_ms, excluded.max_ms)
            """,
            [(*key, c.hits, c.client_errors, c.server_errors, c.total_ms, c.max_ms) for key, c in batch],
        )


def reset() -> None:
    """Oublie les compteurs pas encore écrits et les sessions connues (tests)."""
    with _lock:
        _pending.clear()
    _sessions.clear()
