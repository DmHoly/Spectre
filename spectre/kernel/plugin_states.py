"""L'activation des plugins, réglée par un administrateur pendant que l'application tourne.

Un plugin désactivé reste installé : ses migrations sont appliquées, ses tables et ses fichiers
gardés, ses statiques servis. Ce qui change, à la requête suivante et sans redémarrage
(``spectre.kernel.app``) : ses routes ``/api`` répondent 404 ``plugin_disabled``, ses pages aussi,
ses entrées de la barre du haut disparaissent, et les ``<script>`` / ``<link>`` de ses statiques
sont retirés des pages des autres plugins - un panneau qu'il ajoute à une page ne se charge plus.

- **Effectif** : un plugin est actif s'il est disponible (``Plugin.enabled()``, ex. ``kpis_demo`` sans
  ``SPECTRE_DEMO_DATA``), activé (le choix enregistré, actif par défaut) et si tous les plugins dont il
  dépend le sont. Désactiver un plugin éteint donc ceux qui en dépendent, sans toucher à leur choix
  enregistré : le réactiver les rallume.
- **Noyau** : un plugin ``required``, et tout plugin dont un plugin ``required`` dépend, ne se
  désactive pas (409 ``plugin_required``).

L'état est rangé dans la table ``plugin_states`` - avec ``schema_migrations``, la seule table du
noyau - et lu depuis un cache, vidé à chaque écriture (le serveur tourne en un seul processus).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

from .db import connect, db_path
from .errors import Conflict, NotFound
from .plugin import Plugin

_TABLE = """
CREATE TABLE IF NOT EXISTS plugin_states (
    plugin TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by INTEGER
)
"""


class PluginDisabled(NotFound):
    code = "plugin_disabled"


@dataclass(frozen=True)
class StoredState:
    enabled: bool
    updated_at: str | None = None
    updated_by: int | None = None


_DEFAULT = StoredState(enabled=True)


class PluginStates:
    """L'état des plugins d'une application (``create_app``) : ce qui est enregistré, et ce qui en
    découle pour chacun (:meth:`is_enabled`)."""

    def __init__(self, plugins: Iterable[Plugin]):
        self.plugins: dict[str, Plugin] = {plugin.name: plugin for plugin in plugins}
        self.dependents: dict[str, tuple[str, ...]] = {
            name: tuple(other.name for other in self.plugins.values() if name in other.depends_on) for name in self.plugins
        }
        self.core: frozenset[str] = frozenset(self._core_closure())
        # La disponibilité est lue une fois, à la construction de l'application, comme le montage
        # de ses routes : un plugin indisponible au démarrage n'a pas de routes à rallumer.
        self._available: frozenset[str] = frozenset(name for name, plugin in self.plugins.items() if plugin.enabled())
        self._cache: dict[str, dict[str, StoredState]] = {}
        self._lock = threading.Lock()

    def _core_closure(self) -> set[str]:
        core: set[str] = set()
        pending = [plugin.name for plugin in self.plugins.values() if plugin.required]
        while pending:
            name = pending.pop()
            if name in core or name not in self.plugins:
                continue
            core.add(name)
            pending.extend(self.plugins[name].depends_on)
        return core

    def ensure_table(self) -> None:
        conn = connect()
        try:
            conn.execute(_TABLE)
            conn.commit()
        finally:
            conn.close()

    def stored(self) -> dict[str, StoredState]:
        key = str(db_path())
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        conn = connect()
        try:
            conn.execute(_TABLE)
            rows = conn.execute("SELECT plugin, enabled, updated_at, updated_by FROM plugin_states").fetchall()
        finally:
            conn.close()
        found = {row["plugin"]: StoredState(bool(row["enabled"]), row["updated_at"], row["updated_by"]) for row in rows}
        with self._lock:
            self._cache[key] = found
        return found

    def stored_state(self, name: str) -> StoredState:
        return self.stored().get(name, _DEFAULT)

    def available(self, name: str) -> bool:
        return name in self._available

    def is_enabled(self, name: str) -> bool:
        """Actif : disponible, activé (ou du noyau), et tous ses prérequis actifs. Un nom inconnu
        (hors de cette application) est actif : on ne coupe que ce qu'on gère."""
        return not self.blocked_by(name) if name in self.plugins else True

    def blocked_by(self, name: str) -> list[str]:
        """Pourquoi ``name`` est éteint : ``[name]`` s'il est lui-même désactivé ou indisponible,
        sinon les prérequis désactivés qui l'éteignent (les causes, pas toute la chaîne) ; vide s'il
        est actif."""
        plugin = self.plugins[name]
        if not self.available(name) or (name not in self.core and not self.stored_state(name).enabled):
            return [name]
        causes: list[str] = []
        for dependency in plugin.depends_on:
            for cause in self.blocked_by(dependency) if dependency in self.plugins else ():
                if cause not in causes:
                    causes.append(cause)
        return causes

    def disabled(self) -> set[str]:
        return {name for name in self.plugins if not self.is_enabled(name)}

    def all_dependents(self, name: str) -> list[str]:
        """Les plugins qui dépendent de ``name``, directement ou non, dans l'ordre de la liste."""
        found: set[str] = set()
        pending = list(self.dependents.get(name, ()))
        while pending:
            other = pending.pop()
            if other not in found:
                found.add(other)
                pending.extend(self.dependents.get(other, ()))
        return [other for other in self.plugins if other in found]

    def set_enabled(self, name: str, enabled: bool, user_id: int | None = None) -> None:
        if name not in self.plugins:
            raise NotFound(f"Plugin inconnu : {name}.")
        if name in self.core and not enabled:
            raise Conflict(f"Le plugin « {name} » fait partie du noyau : il ne se désactive pas.", code="plugin_required")
        if not self.available(name) and enabled:
            raise Conflict(f"Le plugin « {name} » n'est pas disponible sur cette instance.", code="plugin_unavailable")
        if self.stored_state(name).enabled == enabled and name in self.stored():
            return
        conn = connect()
        try:
            conn.execute(_TABLE)
            conn.execute(
                "INSERT INTO plugin_states (plugin, enabled, updated_by) VALUES (?, ?, ?) "
                "ON CONFLICT(plugin) DO UPDATE SET enabled = excluded.enabled, "
                "updated_at = datetime('now'), updated_by = excluded.updated_by",
                (name, int(enabled), user_id),
            )
            conn.commit()
        finally:
            conn.close()
        with self._lock:
            self._cache.clear()


_current: PluginStates | None = None


def install(plugins: Iterable[Plugin]) -> PluginStates:
    """Les états des plugins de l'application qu'on construit - ceux que lisent
    :func:`is_enabled` et :func:`current` (la dernière application construite : une seule par
    processus, hors des tests)."""
    global _current
    _current = PluginStates(plugins)
    _current.ensure_table()
    return _current


def current() -> PluginStates | None:
    return _current


def is_enabled(name: str) -> bool:
    """Pour un plugin qui en sert d'autres (``search`` et ses fournisseurs) : ``name`` est-il actif ?
    Vrai hors d'une application construite."""
    return _current is None or _current.is_enabled(name)
