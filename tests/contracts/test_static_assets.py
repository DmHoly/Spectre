"""Chaque fichier du front qu'une page ou un script nomme existe et est servi : un ``<script src>``,
un ``<link href>`` ou un ``<img src>`` local d'une page déclarée par un plugin, et chaque chemin
``/static/...`` écrit en dur dans un script (voir :func:`contracts.frontend_calls.scan_static_urls`).
C'est ce qui rend un déplacement de fichier du front vérifiable : un chemin oublié fait échouer ce
test au lieu de ne répondre 404 que dans le navigateur.
"""

from __future__ import annotations

import re

from contracts.frontend_calls import scan_static_urls
from spectre.kernel.pages import resolve_page
from spectre.plugins import PLUGINS

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ASSET_RE = re.compile(r"<(?:script|img)\b[^>]*\bsrc=\"([^\"]+)\"|<link\b[^>]*\bhref=\"([^\"]+)\"", re.IGNORECASE)


def _page_assets() -> list[tuple[str, str]]:
    """``(page, chemin)`` de chaque fichier local (``/static/...``) que nomme une page déclarée."""
    assets = []
    files = sorted({(plugin.name, page.file) for plugin in PLUGINS for page in plugin.pages})
    for plugin_name, filename in files:
        html = _COMMENT_RE.sub("", resolve_page(plugin_name, filename).read_text(encoding="utf-8"))
        for match in _ASSET_RE.finditer(html):
            url = match.group(1) or match.group(2)
            if url.startswith("/static/") and "${" not in url:
                assets.append((f"{plugin_name}/pages/{filename}", url))
    return assets


def test_every_local_asset_of_a_page_is_served(client):
    assets = _page_assets()
    assert len(assets) > 100  # garde-fou : une expression cassée ne trouverait rien
    missing = [f"{page} {url}" for page, url in assets if client.get(url).status_code != 200]
    assert not missing, "Fichiers nommés par une page mais non servis :\n  " + "\n  ".join(missing)


def test_every_static_path_written_in_a_script_is_served(client):
    urls = scan_static_urls()
    assert urls  # le rapport d'une expérience embarque la feuille de style du noyau
    missing = [str(url) for url in urls if client.get(url.path).status_code != 200]
    assert not missing, "Chemins /static/ écrits dans le front mais non servis :\n  " + "\n  ".join(missing)
