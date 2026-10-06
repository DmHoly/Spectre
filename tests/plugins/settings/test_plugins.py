"""Paramètres > Plugins : un administrateur liste les plugins et en désactive un, à chaud - ses
routes et ses pages répondent 404, il quitte la navigation, ses statiques sont retirés des autres
pages, la recherche ne l'interroge plus ; le noyau ne se désactive pas, et le tout est réservé aux
administrateurs."""

from __future__ import annotations

from support.accounts import login, signup


def _admin(client) -> None:
    signup(client, "boss@example.com", name="Boss")  # le premier compte est administrateur


def _by_name(client) -> dict[str, dict]:
    response = client.get("/api/plugins")
    assert response.status_code == 200
    return {plugin["name"]: plugin for plugin in response.json()}


def test_an_admin_lists_the_plugins_with_their_description_and_state(client):
    _admin(client)
    plugins = _by_name(client)
    assert {"accounts", "settings", "lots", "notebook"} <= plugins.keys()
    lots = plugins["lots"]
    assert lots["title"] == "Lots" and lots["description"] and lots["icon"] == "calendar"
    assert (lots["required"], lots["available"], lots["enabled"], lots["active"]) == (False, True, True, True)
    assert {dep["name"] for dep in lots["depends_on"]} == {"wafers", "areas", "experiments", "search"}
    assert plugins["experiments"]["required"] and plugins["wafers"]["required"] and plugins["settings"]["required"]
    assert {dep["name"] for dep in plugins["characterization"]["dependents"]} == {"notebook"}
    assert not plugins["kpis_demo"]["available"] and not plugins["kpis_demo"]["active"]


def test_disabling_a_plugin_hides_its_routes_pages_navigation_and_assets(client):
    _admin(client)
    assert client.get("/api/lots").status_code == 200
    assert 'href="/lots"' in client.get("/").text

    response = client.patch("/api/plugins/lots", json={"enabled": False})
    assert response.status_code == 200
    body = response.json()
    assert (body["enabled"], body["active"], body["updated_by"]["name"]) == (False, False, "Boss")

    refused = client.get("/api/lots")
    assert (refused.status_code, refused.json()["code"]) == (404, "plugin_disabled")
    page = client.get("/lots")
    assert page.status_code == 404 and "Module désactivé" in page.text

    home = client.get("/").text
    assert 'href="/lots"' not in home
    assert 'data-plugins-off="kpis_demo lots"' in home  # kpis_demo : indisponible sans SPECTRE_DEMO_DATA
    experiment_page = client.get("/microprojets/x/experiences/y").text
    assert "/static/lots/" not in experiment_page and "/static/notebook/" in experiment_page
    assert client.get("/static/lots/client.js").status_code == 200  # les statiques restent servis

    assert client.patch("/api/plugins/lots", json={"enabled": True}).json()["active"]
    assert client.get("/api/lots").status_code == 200
    assert 'data-plugins-off="kpis_demo"' in client.get("/").text


def test_a_disabled_plugin_turns_off_its_dependents_until_it_comes_back(client):
    _admin(client)
    client.patch("/api/plugins/characterization", json={"enabled": False})
    notebook = _by_name(client)["notebook"]
    assert (notebook["enabled"], notebook["active"]) == (True, False)
    assert [dep["name"] for dep in notebook["blocked_by"]] == ["characterization"]

    client.patch("/api/plugins/characterization", json={"enabled": True})
    assert _by_name(client)["notebook"]["active"]


def test_the_search_skips_the_providers_of_a_disabled_plugin(client):
    _admin(client)
    client.patch("/api/plugins/lots", json={"enabled": False})
    assert client.get("/api/search", params={"q": "L1", "type": "lot"}).json() == []
    assert client.get("/api/search", params={"q": "L1"}).status_code == 200


def test_the_core_and_unknown_plugins_are_refused(client):
    _admin(client)
    refused = client.patch("/api/plugins/experiments", json={"enabled": False})
    assert (refused.status_code, refused.json()["code"]) == (409, "plugin_required")
    assert client.patch("/api/plugins/nope", json={"enabled": False}).status_code == 404
    assert client.patch("/api/plugins/lots", json={"enabled": "peut-être"}).status_code == 422


def test_the_settings_are_reserved_to_admins(client):
    _admin(client)
    signup(client, "user@example.com")
    assert client.get("/api/plugins").status_code == 403
    assert client.patch("/api/plugins/lots", json={"enabled": False}).status_code == 403
    login(client, "boss@example.com")
    assert _by_name(client)["lots"]["active"]


def test_the_settings_page_and_its_admin_only_nav_entry(client):
    _admin(client)
    redirect = client.get("/parametres", follow_redirects=False)
    assert (redirect.status_code, redirect.headers["location"]) == (302, "/parametres/plugins")
    page = client.get("/parametres/plugins")
    assert page.status_code == 200 and "settings/plugins.js" in page.text
    # une roue crantée à côté de la session, cachée jusqu'à ce que session.js voie un admin
    assert 'href="/parametres/plugins" class="topbar__icon-btn topbar__tool" data-match="^/parametres" data-admin-only hidden' in page.text
