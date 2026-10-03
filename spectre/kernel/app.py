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

import os
from typing import Sequence

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import data_dir, run_migrations
from .errors import install_error_handlers
from .pages import KERNEL_STATIC_DIR, nav_entries_for, page_handler, plugin_dir, render_nav, resolve_page
from .plugin import Plugin, check_dependencies


def create_app(plugins: Sequence[Plugin] | None = None) -> FastAPI:
    if plugins is None:
        # La racine de composition : le seul endroit du noyau qui lit la liste des plugins.
        from ..plugins import PLUGINS

        plugins = PLUGINS
    check_dependencies(plugins)
    run_migrations(plugins)
    # Le cache disque de PRISM (résultats de hooks par wafer) vit avec le reste des données de
    # Spectre - donc dans le volume monté en production - plutôt que sous ~/.prism/data. Une
    # valeur explicite de PRISM_DATA_DIR reste prioritaire.
    os.environ.setdefault("PRISM_DATA_DIR", str(data_dir() / "prism"))

    app = FastAPI(title="Spectre", docs_url=None, redoc_url=None)
    install_error_handlers(app)

    active = [plugin for plugin in plugins if plugin.enabled()]
    for plugin in active:
        if plugin.router is not None:
            app.include_router(plugin.router)

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

    nav_entries = [entry for plugin in active for entry in plugin.nav]
    for plugin in active:
        for page in plugin.pages:
            nav = render_nav(nav_entries_for(nav_entries, page.path))
            app.get(page.path)(page_handler(resolve_page(plugin.name, page.file), nav))
        if plugin.page_router is not None:
            app.include_router(plugin.page_router)

    return app
