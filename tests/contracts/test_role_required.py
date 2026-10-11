"""Toute écriture dans un µprojet exige au moins le rôle ``editor`` : un ``viewer`` reçoit 403
``forbidden`` sur chaque route d'écriture sous ``/api/microprojects/{microproject_slug}`` (et sur
le µprojet lui-même : modifier, supprimer), lue dans ``app.openapi()`` - une route ajoutée est
couverte d'office, sans test unitaire « un viewer ne peut pas X » par plugin.

Le rôle passe avant tout le reste (``microprojects.deps.require_role`` : une dépendance, résolue
avant le corps) : un 404 (ressource introuvable) ou un 422 (corps invalide) renvoyé à un lecteur
dirait déjà quelque chose de ce qu'il ne peut pas toucher. Une route d'écriture ouverte aux lecteurs
se liste une à une dans ``OPEN_TO_VIEWERS`` ; une entrée qui ne correspond plus à aucune route fait
échouer le test.
"""

from __future__ import annotations

import re
import tempfile

import pytest
from fastapi.testclient import TestClient

from support.accounts import login, signup
from support.microprojects import add_member, create_microproject

MICROPROJECT_PATH = "/api/microprojects/{microproject_slug}"
WRITES = ("POST", "PUT", "PATCH", "DELETE")

# (méthode, chemin) -> pourquoi un lecteur peut l'appeler
OPEN_TO_VIEWERS: dict[tuple[str, str], str] = {}


def _write_operations() -> list[tuple[str, str]]:
    """Les (méthode, chemin) d'écriture d'un µprojet - à la collecte, avant toute fixture, sur un
    dossier de données jetable, avec les plugins optionnels (kpis_demo : SPECTRE_DEMO_DATA=1)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, pytest.MonkeyPatch.context() as env:
        env.setenv("SPECTRE_DATA_DIR", tmp)
        env.setenv("PRISM_DATA_DIR", tmp)
        env.setenv("SPECTRE_DEMO_DATA", "1")
        from spectre.kernel.app import create_app

        paths = create_app().openapi()["paths"]
    return sorted(
        (method.upper(), path)
        for path, operations in paths.items()
        if path == MICROPROJECT_PATH or path.startswith(MICROPROJECT_PATH + "/")
        for method in operations
        if method.upper() in WRITES
    )


def pytest_generate_tests(metafunc):
    if "operation" in metafunc.fixturenames:
        operations = [op for op in _write_operations() if op not in OPEN_TO_VIEWERS]
        metafunc.parametrize("operation", operations, ids=[f"{method} {path}" for method, path in operations])


@pytest.fixture(scope="module")
def viewer_client(tmp_path_factory):
    """Un client connecté en lecteur d'un µprojet « lecture » dont un autre compte est propriétaire."""
    data = tmp_path_factory.mktemp("viewer")
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SPECTRE_DATA_DIR", str(data))
        env.setenv("PRISM_DATA_DIR", str(data / "prism"))
        env.setenv("SPECTRE_DEMO_DATA", "1")
        from spectre.kernel.app import create_app

        with TestClient(create_app()) as client:
            signup(client, "admin-roles@example.com", name="Admin")  # le premier compte est admin
            signup(client, "viewer-roles@example.com", name="Lecteur")
            signup(client, "owner-roles@example.com", name="Owner")
            create_microproject(client, "Lecture")
            add_member(client, "lecture", "viewer-roles@example.com", "viewer")
            login(client, "viewer-roles@example.com")
            yield client


def _url(path: str) -> str:
    return re.sub(r"\{[^}:]+(?::\w+)?\}", lambda m: "lecture" if m.group(0).startswith("{microproject_slug") else "x", path)


def test_the_scanner_sees_the_write_routes():
    operations = _write_operations()
    assert len(operations) > 20
    assert ("POST", MICROPROJECT_PATH + "/experiments") in operations
    assert ("DELETE", MICROPROJECT_PATH) in operations


def test_the_routes_open_to_viewers_still_exist():
    stale = set(OPEN_TO_VIEWERS) - set(_write_operations())
    assert not stale, f"Entrées de OPEN_TO_VIEWERS sans route : {sorted(stale)}"


def test_a_viewer_gets_403_on_every_write(viewer_client, operation):
    method, path = operation
    response = viewer_client.request(method, _url(path), json={})
    assert response.status_code == 403, f"{method} {path} : {response.status_code} {response.text[:200]}"
    assert response.json()["code"] == "forbidden"
