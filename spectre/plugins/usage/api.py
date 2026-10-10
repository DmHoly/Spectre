"""L'utilisation de Spectre over HTTP, admin only (:func:`spectre.plugins.accounts.deps.require_admin`):
``GET /api/usage`` is the report of a period (:func:`.service.report`), filtered by team, account
or plugin. The plugins are those of the running application (``app.state.plugin_states``, as in
``settings``), and a page is named by its HTML ``<title>``.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from ...kernel.errors import NotFound
from ...kernel.pages import resolve_page
from ...kernel.plugin_states import PluginStates
from ..accounts.deps import require_admin
from ..accounts.service import User
from ..teams import service as teams
from . import recorder
from . import service as usage

router = APIRouter(prefix="/api", tags=["usage"])

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_TITLE_SUFFIX_RE = re.compile(r"\s+[—-]\s+Spectre\s*$")


@lru_cache(maxsize=256)
def _page_title(path: Path) -> str | None:
    try:
        match = _TITLE_RE.search(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return _TITLE_SUFFIX_RE.sub("", match.group(1).strip()) if match else None


def _catalog(states: PluginStates) -> tuple[list[usage.PluginInfo], dict[str, str]]:
    """Les plugins dont on mesure l'usage - tous, sauf celui-ci (il ne se compte pas) - et le titre
    de leurs pages."""
    plugins, titles = [], {}
    for plugin in states.plugins.values():
        if plugin.name == recorder.PLUGIN_NAME:
            continue
        plugins.append(usage.PluginInfo(plugin.name, plugin.title or plugin.name, plugin.icon, states.is_enabled(plugin.name)))
        for page in plugin.pages:
            try:
                title = _page_title(resolve_page(plugin.name, page.file))
            except FileNotFoundError:
                continue
            if title:
                titles[page.path] = title
    return plugins, titles


@router.get("/usage")
def get_usage(
    request: Request,
    start: date | None = Query(None, description="premier jour (inclus) ; 29 jours avant la fin par défaut"),
    end: date | None = Query(None, description="dernier jour (inclus) ; aujourd'hui par défaut"),
    granularity: str = Query("day", description="day, week ou month"),
    team: str | None = Query(None, description="le slug d'une équipe : ses membres seulement"),
    user_id: int | None = Query(None),
    plugin: str | None = Query(None, description="un seul module"),
    include_admins: bool = Query(True),
    _user: User = Depends(require_admin),
) -> dict:
    states: PluginStates = request.app.state.plugin_states
    if plugin is not None and plugin not in states.plugins:
        raise NotFound(f"Plugin inconnu : {plugin}.")
    end = end or recorder.now().date()
    start = start or end - timedelta(days=29)
    team_id = teams.get_by_slug(team).id if team else None
    plugins, titles = _catalog(states)
    filters = usage.Filters(start, end, granularity, team_id, user_id, plugin, include_admins)
    return usage.report(filters, plugins, titles)
