"""Toute route de l'API exige une session : un appel anonyme reçoit 401, quelle que soit la route -
lue dans ``app.openapi()``, donc une route ajoutée (ou renommée) est couverte d'office. Seules les
routes publiques de ``/api/auth`` (créer un compte, se connecter...) sont exemptées, une à une
ci-dessous.

L'authentification doit passer avant tout le reste : un 404 (ressource introuvable) ou un 422
(corps invalide) renvoyé à un anonyme dirait déjà quelque chose de ce qui existe.
"""

from __future__ import annotations

import re
import tempfile

import pytest
from fastapi.testclient import TestClient

PUBLIC_ROUTES = {
    ("POST", "/api/auth/register"): "créer un compte",
    ("POST", "/api/auth/login"): "se connecter",
    ("POST", "/api/auth/logout"): "se déconnecter (sans session : rien à fermer)",
    ("POST", "/api/auth/mot-de-passe-oublie"): "demander un lien de réinitialisation",
    ("POST", "/api/auth/reinitialiser"): "choisir un nouveau mot de passe avec ce lien",
    ("GET", "/api/auth/invitation/{token}"): "la page d'inscription lit l'invitation reçue par e-mail",
}


def _api_operations() -> list[tuple[str, str]]:
    """Les (méthode, chemin) de l'API - appelé à la collecte, avant toute fixture : l'application
    est construite sur un dossier de données jetable (importer spectre.api.app en construit déjà une)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, pytest.MonkeyPatch.context() as env:
        env.setenv("SPECTRE_DATA_DIR", tmp)
        env.setenv("PRISM_DATA_DIR", tmp)
        from spectre.api.app import create_app

        paths = create_app().openapi()["paths"]
    return sorted(
        (method.upper(), path) for path, operations in paths.items() if path.startswith("/api/") for method in operations
    )


def pytest_generate_tests(metafunc):
    if "operation" in metafunc.fixturenames:
        operations = [op for op in _api_operations() if op not in PUBLIC_ROUTES]
        metafunc.parametrize("operation", operations, ids=[f"{method} {path}" for method, path in operations])


@pytest.fixture(scope="module")
def anonymous_client(tmp_path_factory):
    data = tmp_path_factory.mktemp("anonymous")
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SPECTRE_DATA_DIR", str(data))
        env.setenv("PRISM_DATA_DIR", str(data / "prism"))
        from spectre.api.app import create_app

        with TestClient(create_app()) as client:
            yield client


def test_public_routes_still_exist():
    operations = set(_api_operations())
    assert not [route for route in PUBLIC_ROUTES if route not in operations], "route publique disparue : mettre PUBLIC_ROUTES à jour"


def test_an_anonymous_caller_gets_401(anonymous_client, operation):
    method, path = operation
    url = re.sub(r"\{[^}]+\}", "1", path)  # 1 : une valeur acceptée par un paramètre texte comme entier
    response = anonymous_client.request(method, url)
    assert response.status_code == 401, f"{method} {path} : {response.status_code} {response.text}"
