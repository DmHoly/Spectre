"""Le plugin PRISM : la page de gestion de PRISM (menu latéral, catalogue des données) dans le menu
Data de la barre du haut, réservée aux administrateurs - son entrée ne se montre qu'à eux -, avec
l'ancienne adresse /donnees qui renvoie vers la nouvelle."""

from __future__ import annotations

import re

from support.accounts import signup
from support.http import plugins_off


def _nav(html: str) -> str:
    return re.search(r"<nav.*?</nav>", html, re.DOTALL).group(0)


def test_the_data_pages_live_under_prism_with_a_side_menu(client):
    signup(client, "boss@example.com", name="Boss")
    for path in ("/prism/donnees", "/prism/donnees/eqe"):
        page = client.get(path)
        assert page.status_code == 200 and 'id="prism-nav"' in page.text and "/static/prism/data-types.js" in page.text
    assert client.get("/static/prism/data-types.js").status_code == 200
    assert client.get("/static/prism/sections.js").status_code == 200


def test_prism_opens_on_its_first_section_and_the_old_data_address_redirects(client):
    signup(client, "boss@example.com", name="Boss")
    home = client.get("/prism", follow_redirects=False)
    assert (home.status_code, home.headers["location"]) == (302, "/prism/donnees")
    legacy = client.get("/donnees", follow_redirects=False)
    assert (legacy.status_code, legacy.headers["location"]) == (302, "/prism/donnees")
    kept = client.get("/donnees/pl?wafers=W12-A3,W12-A4", follow_redirects=False)  # un lien enregistré garde ses plaques
    assert (kept.status_code, kept.headers["location"]) == (302, "/prism/donnees/pl?wafers=W12-A3,W12-A4")


def test_the_data_menu_groups_prism_for_admins_and_the_plate_index(client):
    signup(client, "boss@example.com", name="Boss")
    nav = _nav(client.get("/").text)
    assert nav.count("topbar__group-btn") >= 1 and "<span>Data</span>" in nav
    menu = re.search(r'id="nav-menu-data".*?</div>', nav, re.DOTALL).group(0)
    assert re.findall(r'href="([^"]+)"', menu) == ["/prism/donnees", "/plaques", "/kpi", "/fiche-data"]
    prism_link = re.search(r'<a[^>]*href="/prism/donnees"[^>]*>', menu).group(0)
    assert "data-admin-only" in prism_link  # révélée par la session d'un administrateur seulement
    assert "data-admin-only" not in re.search(r'<a[^>]*href="/plaques"[^>]*>', menu).group(0)
    assert 'href="/donnees"' not in nav


def test_the_old_data_page_is_gone_and_prism_off_hides_its_entry(client):
    signup(client, "boss@example.com", name="Boss")
    assert client.patch("/api/plugins/prism", json={"enabled": False}).json()["active"] is False
    assert client.get("/prism/donnees").status_code == 404
    menu = re.search(r'id="nav-menu-data".*?</div>', _nav(client.get("/").text), re.DOTALL).group(0)
    assert re.findall(r'href="([^"]+)"', menu) == ["/plaques", "/kpi", "/fiche-data"]
    assert "prism" in plugins_off(client.get("/").text)
    experiment_page = client.get("/microprojets/x/experiences/y").text
    assert "prism" in plugins_off(experiment_page)  # le menu « Données en base » ne s'ouvre plus sur PRISM

