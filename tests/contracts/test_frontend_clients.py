"""Le front passe par l'API, et par elle seule, au travers d'un client par plugin (``ARCHITECTURE.md``
§ 1 et § 6) : ``spectre/plugins/<plugin>/static/client.js`` déclare un seul global, ``<plugin>Api``
(camelCase), avec une fonction par appel réseau (ou par URL de ressource binaire). Vérifié sans
navigateur, sur le texte du front (voir :mod:`contracts.frontend_calls`) :

- chaque fonction d'un client vise une route qui existe, avec sa méthode : renommer une URL dans un
  client.js, ou une route côté serveur, fait échouer le test ;
- aucune chaîne ``/api/`` n'est écrite hors des client.js (et du code générique de ``kernel/static/api.js``) ;
- chaque appel ``<plugin>Api.<fonction>(`` du front désigne une fonction qui existe, et chaque fonction
  d'un client sert quelque part.

Les pages du plugin ``docs`` citent des routes dans leur texte : elles restent hors du scan.
"""

from __future__ import annotations

import pytest

from contracts.frontend_calls import client_files, client_globals, matching_route, openapi_routes, scan_api_strings, scan_client_uses, scan_clients
from spectre.plugins import PLUGINS

GENERIC_HTTP_CLIENT = "kernel/static/api.js"


def _camel(plugin_name: str) -> str:
    head, *rest = plugin_name.split("_")
    return head + "".join(part.capitalize() for part in rest) + "Api"


def test_the_scanner_sees_the_clients():
    functions = scan_clients()
    assert len(client_files()) >= 15
    assert len(functions) > 100 and all(f.path for f in functions)


def test_each_client_declares_one_global_named_after_its_plugin():
    plugins = {plugin.name for plugin in PLUGINS}
    problems = []
    for path in client_files():
        plugin = path.parent.parent.name
        declared = client_globals(path)
        if plugin not in plugins:
            problems.append(f"{plugin}/static/client.js : aucun plugin {plugin!r}")
        if declared != [_camel(plugin)]:
            problems.append(f"{plugin}/static/client.js déclare {declared}, au lieu du seul {_camel(plugin)}")
    assert not problems, "\n".join(problems)


def test_every_client_function_targets_an_existing_route(app):
    routes = openapi_routes(app)
    dead = [str(f) for f in scan_clients() if matching_route(f.method, f.path, routes, strict=True) is None]
    assert not dead, "Fonctions de client vers une route qui n'existe pas :\n  " + "\n  ".join(dead)


def test_no_api_url_is_written_outside_the_clients():
    outside = [str(s) for s in scan_api_strings() if not s.file.endswith("/client.js") and s.file != GENERIC_HTTP_CLIENT]
    assert not outside, "Chaînes /api/ hors des client.js (passez par le client du plugin) :\n  " + "\n  ".join(outside)


def test_the_api_string_scanner_sees_the_clients():
    # garde-fou : le scan qui ne trouve rien hors des clients doit trouver leurs URL
    assert len([s for s in scan_api_strings() if s.file.endswith("/client.js")]) > 100


def test_every_client_function_used_by_the_front_exists_and_every_function_is_used():
    functions = {(f.client, f.name) for f in scan_clients()}
    uses = [u for u in scan_client_uses() if not u.file.endswith("/client.js")]
    unknown = [str(u) for u in uses if (u.client, u.name) not in functions]
    used = {(u.client, u.name) for u in uses}
    unused = sorted(f"{client}.{name}" for client, name in functions - used)
    problems = []
    if unknown:
        problems.append("Appels de fonctions de client inexistantes :\n  " + "\n  ".join(unknown))
    if unused:
        problems.append("Fonctions de client que rien n'appelle :\n  " + "\n  ".join(unused))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("before", "after", "function"),
    [
        ('"/api/lots/recherche"', '"/api/lot/recherche"', "search"),
        # un segment littéral renommé que la route paramétrée GET /api/lots/{code} couvrirait
        ('"/api/lots/selection"', '"/api/lots/selectionXX"', "selection"),
    ],
)
def test_a_client_function_renamed_url_is_caught(app, tmp_path, before, after, function):
    # l'expérience « je renomme une URL dans un client.js » : le contrat échoue
    source = next(path for path in client_files() if path.parent.parent.name == "lots")
    root = tmp_path / "spectre"
    target = root / "plugins" / "lots" / "static" / "client.js"
    target.parent.mkdir(parents=True)
    text = source.read_text(encoding="utf-8")
    renamed = text.replace(before, after)
    assert renamed != text
    target.write_text(renamed, encoding="utf-8")
    routes = openapi_routes(app)
    dead = [f for f in scan_clients(root) if matching_route(f.method, f.path, routes, strict=True) is None]
    assert [(f.client, f.name) for f in dead] == [("lotsApi", function)]
