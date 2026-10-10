from __future__ import annotations

import os
from typing import NamedTuple

import pytest


class SentEmail(NamedTuple):
    to: str
    subject: str
    body: str


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Rien de la machine du développeur ne fuit dans un test : ni un serveur SMTP réel, ni les
    données de démo, ni une URL publique configurée - et la bibliothèque racine est un dossier du
    test, initialisé depuis les fichiers livrés à la première lecture (comme sur une nouvelle
    instance) : un test peut la modifier sans toucher au dépôt."""
    for name in list(os.environ):
        if name.startswith("SPECTRE_SMTP_"):
            monkeypatch.delenv(name)
    monkeypatch.delenv("SPECTRE_DEMO_DATA", raising=False)
    monkeypatch.delenv("SPECTRE_BASE_URL", raising=False)

    monkeypatch.setenv("SPECTRE_LIBRARY_DIR", str(tmp_path / "library"))

    from spectre.plugins.experiments import repository as experiments
    from spectre.plugins.library import service as library
    from spectre.plugins.usage import recorder as usage
    from spectre.plugins.wafers import service as plates

    caches = (experiments._CACHE, library._CACHE, plates._CACHE)
    for cache in caches:
        cache.clear()
    usage.reset()  # pas de compteur d'un autre test, écrit dans la base de celui-ci
    yield
    for cache in caches:
        cache.clear()
    usage.reset()


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(path))
    # Le cache PRISM aussi : jamais le vrai ~/.prism/data d'un développeur depuis un test.
    monkeypatch.setenv("PRISM_DATA_DIR", str(path / "prism"))
    return path


@pytest.fixture()
def outbox(monkeypatch):
    """Les e-mails que l'application aurait envoyés (:func:`spectre.kernel.mail.send_email`), dans
    l'ordre - au lieu de les journaliser. Tous les appelants passent par l'attribut du module
    (``mail.send_email``), donc le remplacer là suffit."""
    sent: list[SentEmail] = []

    def capture(to: str, subject: str, body: str) -> None:
        sent.append(SentEmail(to, subject, body))

    monkeypatch.setattr("spectre.kernel.mail.send_email", capture)
    return sent


@pytest.fixture()
def app(data_dir):
    # Imported inside the fixture so SPECTRE_DATA_DIR is already set before spectre.kernel.db is
    # ever asked for a connection.
    from spectre.kernel.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
