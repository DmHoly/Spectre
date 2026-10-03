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
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Callable, Iterable

from fastapi.responses import FileResponse, HTMLResponse, Response

from .plugin import NavEntry

TOPBAR_MARKER = "<!-- spectre:topbar -->"
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
    <div class="topbar__actions">
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


def render_nav(entries: Iterable[NavEntry]) -> str:
    """La navigation principale, dans l'ordre des entrées (``order``). ``data-match`` porte
    l'expression régulière de la section, lue par ``kernel/static/shell.js``."""
    links = []
    for entry in sorted(entries, key=lambda e: (e.order, e.label)):
        element_id = f' id="{escape(entry.id)}"' if entry.id else ""
        match = f' data-match="{escape(entry.match)}"' if entry.match else ""
        links.append(f'      <a href="{escape(entry.href)}" class="topbar__link"{element_id}{match}>{escape(entry.label)}</a>')
    return '<nav class="topbar__nav" aria-label="Navigation principale">\n' + "\n".join(links) + "\n    </nav>"


def render_topbar(nav: str, crumb_id: str | None = None, crumb_text: str | None = None) -> str:
    """La barre du haut complète, avec ``nav`` (:func:`render_nav`) et le fil d'Ariane de la page."""
    crumb = ""
    if crumb_id is not None or crumb_text is not None:
        element_id = f' id="{escape(crumb_id)}"' if crumb_id else ""
        crumb = f'\n      <span class="topbar__crumb"{element_id}>{escape(crumb_text or "", quote=False)}</span>'
    return _TOPBAR_TEMPLATE.format(crumb=crumb, nav=nav)


def _replace_marker(match: re.Match, nav: str) -> str:
    attributes = dict(_CRUMB_ATTR_RE.findall(match.group(1)))
    return render_topbar(nav, attributes.get("id"), attributes.get("text"))


def page_response(path: Path, nav: str) -> Response:
    """La page ``path``, avec la barre du haut (navigation ``nav``) à la place du marqueur s'il y
    figure - sinon le fichier lui-même (et son ``ETag``)."""
    html = path.read_text(encoding="utf-8")
    if TOPBAR_MARKER_RE.search(html):
        return HTMLResponse(TOPBAR_MARKER_RE.sub(lambda m: _replace_marker(m, nav), html))
    return FileResponse(path)


def page_handler(path: Path, nav: str) -> Callable[[], Response]:
    def handler() -> Response:
        return page_response(path, nav)

    return handler
