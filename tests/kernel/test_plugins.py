"""Les manifestes des plugins : l'ordre de ``PLUGINS`` (vérifié au démarrage), le service de chaque
page déclarée, et ce que le noyau construit à partir d'un manifeste (pages, barre du haut, statiques).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from spectre.kernel import pages
from spectre.kernel.app import create_app
from spectre.kernel.plugin import NavEntry, Page, Plugin, PluginOrderError, check_dependencies
from spectre.plugins import PLUGINS

from support.accounts import signup

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "spectre" / "plugins"


def test_check_dependencies_rejects_a_dependency_listed_after_its_dependent():
    with pytest.raises(PluginOrderError, match="lots"):
        check_dependencies([Plugin("lots", depends_on=("wafers",)), Plugin("wafers")])


def test_check_dependencies_rejects_an_unknown_dependency_and_a_duplicate():
    with pytest.raises(PluginOrderError, match="search"):
        check_dependencies([Plugin("accounts"), Plugin("microprojects", depends_on=("accounts", "search"))])
    with pytest.raises(PluginOrderError, match="deux fois"):
        check_dependencies([Plugin("accounts"), Plugin("accounts")])


def test_the_plugin_list_is_in_topological_order_and_matches_the_packages():
    check_dependencies(PLUGINS)
    packages = sorted(path.parent.name for path in PLUGINS_DIR.glob("*/__init__.py"))
    assert sorted(plugin.name for plugin in PLUGINS) == packages


def _page_url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def test_every_declared_page_is_served(client):
    signup(client, "pages@example.com")
    declared = [(plugin.name, page) for plugin in PLUGINS if plugin.enabled() for page in plugin.pages]
    assert len(declared) > 30
    for plugin_name, page in declared:
        response = client.get(_page_url(page.path), follow_redirects=False)
        assert response.status_code == 200, f"{plugin_name} {page.path} : {response.status_code}"
        assert response.headers["content-type"].startswith("text/html")


def test_the_special_page_routes_redirect(client):
    signup(client, "redirects@example.com")
    routes = [route for plugin in PLUGINS if plugin.page_router for route in plugin.page_router.routes]
    assert routes
    for route in routes:
        response = client.get(_page_url(route.path), follow_redirects=False)
        assert response.status_code in (301, 302, 307, 308), f"{route.path} : {response.status_code}"


@pytest.fixture()
def showcase(tmp_path, monkeypatch, data_dir):
    """Un plugin de démonstration, ``vitrine``, avec ses propres pages et statiques."""
    monkeypatch.setattr(pages, "PLUGINS_DIR", tmp_path / "plugins")
    root = tmp_path / "plugins" / "vitrine"
    (root / "pages").mkdir(parents=True)
    (root / "static").mkdir()
    (root / "pages" / "vitrine.html").write_text(
        f"<html><body><div class='topbar'>{pages.TOPBAR_MARKER}</div></body></html>", encoding="utf-8"
    )
    (root / "pages" / "brute.html").write_text("<html><body>sans barre commune</body></html>", encoding="utf-8")
    (root / "static" / "client.js").write_text("const vitrineApi = {};", encoding="utf-8")
    redirects = APIRouter()
    redirects.get("/v/{code}")(lambda code: {"code": code})
    plugin = Plugin(
        "vitrine",
        pages=(Page("/vitrine", "vitrine.html"), Page("/vitrine/brute", "brute.html")),
        nav=(NavEntry("Docs", "/docs", order=20), NavEntry("Vitrine & co", "/vitrine", order=10, match=r"^/vitrine")),
        page_router=redirects,
    )
    with TestClient(create_app([plugin])) as client:
        yield client


def test_the_topbar_marker_is_replaced_by_the_navigation_of_every_plugin(showcase):
    html = showcase.get("/vitrine").text
    assert pages.TOPBAR_MARKER not in html
    nav = re.search(r'<nav class="topbar__nav".*?</nav>', html).group(0)
    assert re.findall(r'href="([^"]+)"', nav) == ["/vitrine", "/docs"]  # dans l'ordre des entrées
    assert 'data-match="^/vitrine"' in nav and "Vitrine &amp; co" in nav


def test_a_page_without_the_marker_is_served_as_is(showcase):
    response = showcase.get("/vitrine/brute")
    assert response.text == "<html><body>sans barre commune</body></html>"
    assert response.headers["cache-control"] == "no-cache"


def test_a_plugin_static_folder_is_served_under_its_name(showcase):
    response = showcase.get("/static/vitrine/client.js")
    assert response.status_code == 200 and "vitrineApi" in response.text
    assert showcase.get("/v/abc").json() == {"code": "abc"}


def test_a_page_absent_from_its_plugin_fails_at_start_up(tmp_path, monkeypatch, data_dir):
    monkeypatch.setattr(pages, "PLUGINS_DIR", tmp_path / "plugins")
    with pytest.raises(FileNotFoundError, match="absente.html"):
        create_app([Plugin("vitrine", pages=(Page("/vitrine", "absente.html"),))])


def test_a_disabled_plugin_brings_neither_routes_nor_pages(data_dir):
    router = APIRouter()
    router.get("/api/vitrine")(lambda: {"ok": True})
    plugin = Plugin("vitrine", router=router, pages=(Page("/vitrine", "index.html"),), enabled=lambda: False)
    with TestClient(create_app([plugin])) as client:
        assert client.get("/api/vitrine").status_code == 404
        assert client.get("/vitrine").status_code == 404
