"""Un verrou par clé (``keyed_lock("experiments", slug)``) : le serveur tourne en un seul processus,
un ``threading.Lock`` suffit à sérialiser les écritures sur une même ressource. Les verrous ne sont
jamais libérés de la table - un par µprojet, par exemple, reste une poignée d'objets.
"""

from __future__ import annotations

import threading

_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_GUARD = threading.Lock()


def keyed_lock(namespace: str, key: str) -> threading.Lock:
    """Le verrou de ``key`` dans ``namespace`` - toujours le même objet pour la même paire."""
    with _GUARD:
        return _LOCKS.setdefault((namespace, key), threading.Lock())
