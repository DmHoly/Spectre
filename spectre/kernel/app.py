"""The Spectre FastAPI application: a real multi-page site (each screen is its own HTML file and
URL, not a client-routed single shell) plus the JSON API backing it - both brought by the plugins
(``spectre.plugins.PLUGINS``), which this module only assembles.

Deep domain logic never lives here: structure simulation comes from ``structureforge``, experiment
versioning/DOE/diffing/graphing come from ``follow``, and what neither of those has (accounts,
microprojects, permissions, the pages that tie them into one workflow) lives in the plugins.

No application is built at import time: uvicorn runs :func:`create_app` as a factory
(``spectre.kernel.app:create_app``, see :mod:`spectre.cli`).
"""

from __future__ import annotations

from typing import Sequence

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from . import plugin_states
from .db import run_migrations
from .errors import install_error_handlers
from .pages import KERNEL_STATIC_DIR, nav_entries_for, page_handler, plugin_dir, render_topbar_parts, resolve_page
from .plugin import NavEntry, Plugin, check_dependencies
from .plugin_states import PluginDisabled, PluginStates


def _guard(states: PluginStates, plugin: Plugin):
    """La dépendance posée sur toutes les routes d'un plugin : 404 ``plugin_disabled`` s'il est éteint."""

    def require_enabled() -> None:
        if not states.is_enabled(plugin.name):
            raise PluginDisabled(f"Le module « {plugin.title or plugin.name} » est désactivé.")

    return require_enabled


def _nav_renderer(states: PluginStates, entries: list[tuple[str, NavEntry]], page_path: str):
    """La navigation d'une page, sans les entrées des plugins éteints - relue à chaque requête."""

    def nav():
        off = states.disabled()
        return render_topbar_parts(nav_entries_for([entry for owner, entry in entries if owner not in off], page_path))

    return nav


def create_app(plugins: Sequence[Plugin] | None = None) -> FastAPI:
    if plugins is None:
        # La racine de composition : le seul endroit du noyau qui lit la liste des plugins.
        from ..plugins import PLUGINS

        plugins = PLUGINS
    check_dependencies(plugins)
    run_migrations(plugins)

    app = FastAPI(title="Spectre", docs_url=None, redoc_url=None)
    install_error_handlers(app)
    # L'activation des plugins se règle à chaud (spectre.kernel.plugin_states) : tout plugin
    # disponible est monté, et chacune de ses routes vérifie à la requête qu'il est actif.
    states = plugin_states.install(plugins)
    app.state.plugin_states = states

    active = [plugin for plugin in plugins if plugin.enabled()]
    for plugin in active:
        if plugin.router is not None:
            app.include_router(plugin.router, dependencies=[Depends(_guard(states, plugin))])

    if KERNEL_STATIC_DIR.is_dir():
        app.mount("/static/kernel", StaticFiles(directory=KERNEL_STATIC_DIR), name="static-kernel")
    for plugin in active:
        static_dir = plugin_dir(plugin.name) / "static"
        if static_dir.is_dir():
            app.mount(f"/static/{plugin.name}", StaticFiles(directory=static_dir), name=f"static-{plugin.name}")

    @app.middleware("http")
    async def _revalidate_pages_and_assets(request, call_next):
        """The HTML pages and everything under ``/static`` are served straight from files that
        change on every deploy - tell the browser to revalidate (cheap: the responses carry an
        ETag - ``StaticFiles`` for the assets, :func:`~spectre.kernel.pages.page_response` for the
        pages - so an unchanged one comes back 304) instead of serving a stale copy.
        Without this a JS/CSS/HTML change only shows after a manual hard-refresh.
        """
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if request.url.path.startswith("/static/") or content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    nav_entries = [(plugin.name, entry) for plugin in active for entry in plugin.nav]
    for plugin in active:
        # ses routes de pages spéciales d'abord : une redirection peut viser un gabarit plus
        # étroit qu'une page du plugin (un ancien id de version sous la page d'une étude)
        if plugin.page_router is not None:
            app.include_router(plugin.page_router, dependencies=[Depends(_guard(states, plugin))])
        for page in plugin.pages:
            nav = _nav_renderer(states, nav_entries, page.path)
            app.get(page.path)(page_handler(resolve_page(plugin.name, page.file), nav, states.disabled, plugin.name))

    return app
