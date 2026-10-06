"""L'activation des plugins (``spectre.kernel.plugin_states``) : le noyau ne se désactive pas, un
plugin éteint éteint ceux qui en dépendent sans toucher à leur choix, et l'état survit à une
nouvelle instance (il est en base)."""

from __future__ import annotations

import pytest

from spectre.kernel.errors import Conflict, NotFound
from spectre.kernel.plugin import Plugin
from spectre.kernel.plugin_states import PluginStates

PLUGINS = (
    Plugin("accounts", required=True),
    Plugin("library"),
    Plugin("core", depends_on=("accounts", "library"), required=True),
    Plugin("wafers", depends_on=("core",)),
    Plugin("lots", depends_on=("wafers",)),
    Plugin("atlas", depends_on=("lots",)),
    Plugin("demo", depends_on=("core",), enabled=lambda: False),
)


@pytest.fixture()
def states(data_dir):
    found = PluginStates(PLUGINS)
    found.ensure_table()
    return found


def test_the_core_is_the_required_plugins_and_what_they_depend_on(states):
    assert states.core == {"accounts", "library", "core"}
    with pytest.raises(Conflict) as refused:
        states.set_enabled("library", False)
    assert refused.value.code == "plugin_required"
    assert states.is_enabled("library")


def test_every_plugin_is_enabled_by_default_except_an_unavailable_one(states):
    assert states.disabled() == {"demo"}
    assert states.blocked_by("demo") == ["demo"]
    with pytest.raises(Conflict) as refused:
        states.set_enabled("demo", True)
    assert refused.value.code == "plugin_unavailable"


def test_disabling_a_plugin_turns_off_its_dependents_without_changing_their_choice(states):
    states.set_enabled("wafers", False, user_id=7)
    assert states.disabled() == {"wafers", "lots", "atlas", "demo"}
    assert states.blocked_by("atlas") == ["wafers"]
    assert states.stored_state("lots").enabled
    assert states.all_dependents("wafers") == ["lots", "atlas"]

    states.set_enabled("lots", False)
    states.set_enabled("wafers", True)
    assert states.disabled() == {"lots", "atlas", "demo"}
    assert states.blocked_by("atlas") == ["lots"]


def test_the_state_is_stored_and_read_by_a_new_instance(states):
    states.set_enabled("lots", False, user_id=3)
    again = PluginStates(PLUGINS)
    assert not again.is_enabled("lots")
    stored = again.stored_state("lots")
    assert (stored.enabled, stored.updated_by) == (False, 3) and stored.updated_at


def test_an_unknown_plugin_is_refused_and_a_foreign_name_reads_as_enabled(states):
    with pytest.raises(NotFound):
        states.set_enabled("nope", False)
    assert states.is_enabled("nope")
