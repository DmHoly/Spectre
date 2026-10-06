"""Le service des pages HTML des plugins : chaque :class:`~spectre.kernel.plugin.Page` est un
fichier de ``plugins/<plugin>/pages/``, servi tel quel - sauf le marqueur ``<!-- spectre:topbar -->``,
remplacé par la barre du haut commune : la marque, le fil d'Ariane de la page, la navigation
principale construite à partir des :class:`~spectre.kernel.plugin.NavEntry` de tous les plugins
actifs, et la place de la session (nom, initiales et déconnexion, remplis par
``accounts/static/session.js``) ; la recherche s'y insère d'elle-même (``search/static/topbar-search.js``).
Une page qui ne porte pas le marqueur garde sa propre barre du haut (ou n'en a pas).

Le fil d'Ariane se déclare dans le marqueur : ``<!-- spectre:topbar crumb-id="crumb" crumb-text="/ Lots" -->``
(``crumb-id`` : l'id que le script de la page remplit ; ``crumb-text`` : son texte initial). Sans
l'un ni l'autre, la barre n'a pas de fil d'Ariane.

Les plugins éteints (``spectre.kernel.plugin_states``) sont relus à chaque requête : leurs entrées
quittent la navigation, les ``<script>`` et ``<link>`` qui chargent leurs statiques
(``/static/<plugin>/...``) sont retirés de la page, et la balise ``<html>`` les nomme
(``data-plugins-off``, lu par ``pluginEnabled`` de ``kernel/static/ui.js``). Une entrée réservée aux
administrateurs (``NavEntry.admin``) est rendue cachée ; ``accounts/static/session.js`` la révèle.
"""

from __future__ import annotations

import hashlib
import re
from email.utils import formatdate
from html import escape
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from .plugin import NavEntry

TOPBAR_MARKER_RE = re.compile(r'<!-- spectre:topbar((?:\s+crumb-(?:id|text)="[^"]*")*)\s*-->')
_CRUMB_ATTR_RE = re.compile(r'crumb-(id|text)="([^"]*)"')
PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
KERNEL_STATIC_DIR = Path(__file__).resolve().parent / "static"

# La barre du haut, à l'indentation des pages (le marqueur est à deux espaces, dans <body>).
_TOPBAR_TEMPLATE = """<div class="topbar">
    <div class="topbar__brand">
      <a href="/" class="topbar__home" aria-label="Spectre - accueil">
        <img class="brand-logo" src="/static/kernel/img/aledia-logo.svg" alt="Aledia" width="71" height="28">
        <span class="topbar__sep" aria-hidden="true"></span>
        <span class="topbar__product">Spectre</span>
      </a>{crumb}
    </div>
    {nav}
    <div class="topbar__actions">{tools}
      <a href="/profil" class="topbar__user" title="Mon profil">
        <span class="js-user-name topbar__user-name"></span>
        <span class="avatar js-user-initials" aria-hidden="true"></span>
      </a>
      <a href="#" class="js-logout topbar__icon-btn" aria-label="Se déconnecter" title="Se déconnecter"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg></a>
    </div>
  </div>"""


def plugin_dir(plugin_name: str) -> Path:
    return PLUGINS_DIR / plugin_name


def resolve_page(plugin_name: str, filename: str) -> Path:
    """Le fichier d'une page, dans ``pages/`` du plugin."""
    path = plugin_dir(plugin_name) / "pages" / filename
    if not path.is_file():
        raise FileNotFoundError(f"page {filename!r} du plugin {plugin_name!r} introuvable")
    return path


def nav_entries_for(entries: Iterable[NavEntry], page_path: str) -> list[NavEntry]:
    """Les entrées de la barre du haut d'une page (``page_path`` : le gabarit de sa route) : toutes,
    sauf celles réservées à d'autres pages (``NavEntry.pages``)."""
    return [entry for entry in entries if not entry.pages or page_path in entry.pages]


class TopbarParts(NamedTuple):
    """Ce que les plugins mettent dans la barre du haut : la navigation (``nav``, :func:`render_nav`)
    et les boutons à icône, à côté de la session (``tools``, :func:`render_tools`)."""

    nav: str
    tools: str = ""


def render_tools(entries: Iterable[NavEntry]) -> str:
    """Les entrées à icône (``NavEntry.icon``) : un bouton par entrée, à gauche de la session,
    nommé par son libellé (``aria-label``, ``title``) ; ``data-match`` comme la navigation."""
    buttons = []
    for entry in sorted(entries, key=lambda e: (e.order, e.label)):
        element_id = f' id="{escape(entry.id)}"' if entry.id else ""
        match = f' data-match="{escape(entry.match)}"' if entry.match else ""
        admin = " data-admin-only hidden" if entry.admin else ""
        label = escape(entry.label)
        svg = (
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{entry.icon}</svg>'
        )
        buttons.append(
            f'\n      <a href="{escape(entry.href)}" class="topbar__icon-btn topbar__tool"{element_id}{match}{admin} '
            f'aria-label="{label}" title="{label}">{svg}</a>'
        )
    return "".join(buttons)


def render_topbar_parts(entries: Iterable[NavEntry]) -> TopbarParts:
    """La navigation (entrées sans icône) et les boutons (entrées à icône) d'une page."""
    entries = list(entries)
    return TopbarParts(render_nav([e for e in entries if not e.icon]), render_tools([e for e in entries if e.icon]))


def render_nav(entries: Iterable[NavEntry]) -> str:
    """La navigation principale, dans l'ordre des entrées (``order``). ``data-match`` porte
    l'expression régulière de la section, lue par ``kernel/static/shell.js``."""
    links = []
    for entry in sorted(entries, key=lambda e: (e.order, e.label)):
        element_id = f' id="{escape(entry.id)}"' if entry.id else ""
        match = f' data-match="{escape(entry.match)}"' if entry.match else ""
        admin = " data-admin-only hidden" if entry.admin else ""
        links.append(f'      <a href="{escape(entry.href)}" class="topbar__link"{element_id}{match}{admin}>{escape(entry.label)}</a>')
    return '<nav class="topbar__nav" aria-label="Navigation principale">\n' + "\n".join(links) + "\n    </nav>"


def render_topbar(nav: str | TopbarParts, crumb_id: str | None = None, crumb_text: str | None = None) -> str:
    """La barre du haut complète, avec ``nav`` (:func:`render_nav`, ou :class:`TopbarParts` avec
    ses boutons) et le fil d'Ariane de la page."""
    parts = nav if isinstance(nav, TopbarParts) else TopbarParts(nav)
    crumb = ""
    if crumb_id is not None or crumb_text is not None:
        element_id = f' id="{escape(crumb_id)}"' if crumb_id else ""
        crumb = f'\n      <span class="topbar__crumb"{element_id}>{escape(crumb_text or "", quote=False)}</span>'
    return _TOPBAR_TEMPLATE.format(crumb=crumb, nav=parts.nav, tools=parts.tools)


def _replace_marker(match: re.Match, nav: str | TopbarParts) -> str:
    attributes = dict(_CRUMB_ATTR_RE.findall(match.group(1)))
    return render_topbar(nav, attributes.get("id"), attributes.get("text"))


def render_page(path: Path, nav: str | TopbarParts) -> str:
    """Le HTML de la page ``path``, avec la barre du haut (navigation ``nav``) à la place du
    marqueur s'il y figure - sinon le fichier tel quel."""
    html = path.read_text(encoding="utf-8")
    return TOPBAR_MARKER_RE.sub(lambda m: _replace_marker(m, nav), html)


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    tags = [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]
    return "*" in tags or etag in tags


def without_plugins(html: str, disabled: Iterable[str]) -> str:
    """``html`` sans les ``<script src>`` ni les ``<link href>`` qui chargent les statiques des
    plugins ``disabled``, sa balise ``<html>`` marquée ``data-plugins-off="a b"``."""
    names = sorted(disabled)
    if not names:
        return html
    asset = r'"/static/(?:' + "|".join(re.escape(name) for name in names) + r')/[^"]*"'
    html = re.sub(r"[ \t]*<script\b[^>]*\bsrc=" + asset + r"[^>]*>\s*</script>[ \t]*\r?\n?", "", html)
    html = re.sub(r"[ \t]*<link\b[^>]*\bhref=" + asset + r"[^>]*>[ \t]*\r?\n?", "", html)
    return re.sub(r"<html\b", f'<html data-plugins-off="{escape(" ".join(names))}"', html, count=1)


def page_response(path: Path, nav: str | TopbarParts, request: Request | None = None, disabled: Iterable[str] = ()) -> Response:
    """La page rendue (:func:`render_page`, sans les statiques des plugins ``disabled``), avec un
    ``ETag`` (empreinte du HTML servi, barre du haut comprise) et un ``Last-Modified`` (date du
    fichier) ; une revalidation dont le ``If-None-Match`` porte cet ``ETag`` reçoit un 304 sans corps."""
    html = without_plugins(render_page(path, nav), disabled)
    etag = '"' + hashlib.sha256(html.encode("utf-8")).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Last-Modified": formatdate(path.stat().st_mtime, usegmt=True)}
    if request is not None and _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return HTMLResponse(html, headers=headers)


_DISABLED_PAGE = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Module désactivé — Spectre</title>
  <link rel="stylesheet" href="/static/kernel/kernel.css">
</head>
<body>
  {topbar}
  <div class="page" style="padding-top:60px;">
    <div class="empty-state">
      <h1 style="font-size:20px;margin-bottom:8px;">Module désactivé</h1>
      <p>Cette page appartient à un module qu'un administrateur a désactivé.</p>
      <p style="margin-top:16px;"><a href="/" class="btn btn-line">Retour à l'accueil</a></p>
    </div>
  </div>
  <script src="/static/kernel/api.js"></script>
  <script src="/static/kernel/ui.js"></script>
  <script src="/static/kernel/shell.js"></script>
  <script src="/static/accounts/client.js"></script>
  <script src="/static/accounts/session.js"></script>
</body>
</html>
"""


def disabled_page(nav: str | TopbarParts) -> HTMLResponse:
    """La page d'un plugin éteint : un 404 qui garde la barre du haut."""
    return HTMLResponse(_DISABLED_PAGE.format(topbar=render_topbar(nav)), status_code=404)


def page_handler(
    path: Path,
    nav: Callable[[], str | TopbarParts],
    disabled: Callable[[], set[str]] = set,
    plugin_name: str | None = None,
) -> Callable[[Request], Response]:
    """Le handler d'une page : sa navigation (``nav()``) et les plugins éteints (``disabled()``),
    relus à chaque requête ; la page d'un plugin éteint (``plugin_name``) est :func:`disabled_page`."""

    def handler(request: Request) -> Response:
        off = disabled()
        if plugin_name is not None and plugin_name in off:
            return disabled_page(nav())
        return page_response(path, nav(), request, off)

    return handler
