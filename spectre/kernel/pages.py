"""Le service des pages HTML des plugins : chaque :class:`~spectre.kernel.plugin.Page` est un
fichier de ``plugins/<plugin>/pages/``, servi tel quel - sauf le marqueur ``<!-- spectre:topbar -->``,
remplacé par la navigation principale construite à partir des :class:`~spectre.kernel.plugin.NavEntry`
de tous les plugins actifs. Une page qui ne porte pas le marqueur garde sa propre barre du haut.

Tant que les pages n'ont pas rejoint leur plugin, un fichier absent de ``pages/`` est cherché dans
:data:`LEGACY_STATIC_DIR`, l'ancien dossier commun.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Iterable

from fastapi.responses import FileResponse, HTMLResponse, Response

from .plugin import NavEntry

TOPBAR_MARKER = "<!-- spectre:topbar -->"
PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
KERNEL_STATIC_DIR = Path(__file__).resolve().parent / "static"
# Repli transitoire : les pages et le front de tous les plugins, servis sous /static.
LEGACY_STATIC_DIR = Path(__file__).resolve().parents[1] / "api" / "static"


def plugin_dir(plugin_name: str) -> Path:
    return PLUGINS_DIR / plugin_name


def resolve_page(plugin_name: str, filename: str) -> Path:
    """Le fichier d'une page : dans ``pages/`` du plugin, sinon dans :data:`LEGACY_STATIC_DIR`."""
    for candidate in (plugin_dir(plugin_name) / "pages" / filename, LEGACY_STATIC_DIR / filename):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"page {filename!r} du plugin {plugin_name!r} introuvable")


def render_nav(entries: Iterable[NavEntry]) -> str:
    """La navigation principale, dans l'ordre des entrées (``order``)."""
    links = []
    for entry in sorted(entries, key=lambda e: (e.order, e.label)):
        match = f' data-match="{escape(entry.match)}"' if entry.match else ""
        links.append(f'<a href="{escape(entry.href)}" class="topbar__link"{match}>{escape(entry.label)}</a>')
    return '<nav class="topbar__nav" aria-label="Navigation principale">' + "".join(links) + "</nav>"


def page_response(path: Path, topbar: str) -> Response:
    """La page ``path``, avec ``topbar`` à la place du marqueur s'il y figure - sinon le fichier
    lui-même (et son ``ETag``)."""
    html = path.read_text(encoding="utf-8")
    if TOPBAR_MARKER in html:
        return HTMLResponse(html.replace(TOPBAR_MARKER, topbar))
    return FileResponse(path)


def page_handler(path: Path, topbar: str) -> Callable[[], Response]:
    def handler() -> Response:
        return page_response(path, topbar)

    return handler
