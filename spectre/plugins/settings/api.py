"""Settings over HTTP, admin only (:func:`spectre.plugins.accounts.deps.require_admin`):
``/api/plugins`` lists the application's plugins with their state, ``PATCH /api/plugins/{plugin_name}``
turns one on or off - live, no restart (:mod:`spectre.kernel.plugin_states`). A plugin of the core
answers 409 ``plugin_required``, one not available on this instance 409 ``plugin_unavailable``.

The states are those of the running application (``app.state.plugin_states``, set by
``create_app``): this plugin can't import the plugin list, which imports it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ...kernel.errors import NotFound
from ...kernel.plugin_states import PluginStates
from ..accounts.deps import require_admin
from ..accounts.service import User
from . import service as settings
from .schemas import PluginPatch

router = APIRouter(prefix="/api", tags=["settings"])
page_router = APIRouter()


def _states(request: Request) -> PluginStates:
    return request.app.state.plugin_states


def _known(states: PluginStates, plugin_name: str) -> str:
    if plugin_name not in states.plugins:
        raise NotFound(f"Plugin inconnu : {plugin_name}.")
    return plugin_name


@page_router.get("/parametres", include_in_schema=False)
def settings_home() -> RedirectResponse:
    """Les paramètres s'ouvrent sur leur première section."""
    return RedirectResponse("/parametres/plugins", status_code=302)


@router.get("/plugins")
def list_plugins(request: Request, _user: User = Depends(require_admin)) -> list[dict]:
    return settings.describe_all(_states(request))


@router.get("/plugins/{plugin_name}")
def get_plugin(plugin_name: str, request: Request, _user: User = Depends(require_admin)) -> dict:
    states = _states(request)
    return settings.describe(states, _known(states, plugin_name))


@router.patch("/plugins/{plugin_name}")
def update_plugin(plugin_name: str, body: PluginPatch, request: Request, user: User = Depends(require_admin)) -> dict:
    states = _states(request)
    return settings.set_enabled(states, _known(states, plugin_name), body.enabled, user.id)
