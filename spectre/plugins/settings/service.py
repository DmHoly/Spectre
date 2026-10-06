"""Les paramètres de l'application, réservés aux administrateurs. Première section : les plugins,
leur description et leur activation, dont la règle est au noyau (:mod:`spectre.kernel.plugin_states`) -
ce module n'en fait que la vue."""

from __future__ import annotations

from ...kernel.plugin_states import PluginStates
from ..accounts import service as accounts


def _title(states: PluginStates, name: str) -> str:
    return states.plugins[name].title or name


def describe(states: PluginStates, name: str) -> dict:
    """Un plugin tel que la page le montre : ce qu'il est, son choix enregistré (``enabled``) et ce
    qui en découle (``active``, ``blocked_by`` : les plugins éteints qui l'éteignent), ce dont il
    dépend et ce qui dépend de lui (``dependents`` : ce que le désactiver éteindrait)."""
    plugin = states.plugins[name]
    stored = states.stored_state(name)
    author = accounts.get_by_id(stored.updated_by) if stored.updated_by is not None else None
    blocked = [other for other in states.blocked_by(name) if other != name]
    return {
        "name": name,
        "title": _title(states, name),
        "description": plugin.description,
        "icon": plugin.icon,
        "required": name in states.core,
        "available": states.available(name),
        "enabled": name in states.core or stored.enabled,
        "active": states.is_enabled(name),
        "blocked_by": [{"name": other, "title": _title(states, other)} for other in blocked],
        "depends_on": [{"name": other, "title": _title(states, other)} for other in plugin.depends_on],
        "dependents": [
            {"name": other, "title": _title(states, other), "active": states.is_enabled(other)} for other in states.all_dependents(name)
        ],
        "updated_at": stored.updated_at,
        "updated_by": {"id": author.id, "name": author.name} if author else None,
    }


def describe_all(states: PluginStates) -> list[dict]:
    """Les plugins dans l'ordre de la liste (l'ordre topologique)."""
    return [describe(states, name) for name in states.plugins]


def set_enabled(states: PluginStates, name: str, enabled: bool, user_id: int) -> dict:
    states.set_enabled(name, enabled, user_id)
    return describe(states, name)
