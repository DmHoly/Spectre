from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

LIBRARY_DIR = Path(__file__).resolve().parents[1] / "library"


class SentEmail(NamedTuple):
    to: str
    subject: str
    body: str


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Rien de la machine du développeur ne fuit dans un test : ni un serveur SMTP réel, ni les
    données de démo, ni une URL publique configurée - et la bibliothèque racine (``library/``) est
    une copie, qu'un test peut modifier sans toucher au dépôt."""
    for name in list(os.environ):
        if name.startswith("SPECTRE_SMTP_"):
            monkeypatch.delenv(name)
    monkeypatch.delenv("SPECTRE_DEMO_DATA", raising=False)
    monkeypatch.delenv("SPECTRE_BASE_URL", raising=False)

    library = tmp_path / "library"
    shutil.copytree(LIBRARY_DIR, library)
    monkeypatch.setenv("SPECTRE_LIBRARY_DIR", str(library))

    # Caches indexés par nom de fichier et mtime - or copytree conserve le mtime : sans les vider,
    # un test lirait le contenu qu'un test précédent a mis en cache pour le même fichier.
    from spectre.core import plates, registry

    caches = (registry._CACHE, registry._MAPPING_CACHE, plates._CACHE)
    for cache in caches:
        cache.clear()
    yield
    for cache in caches:
        cache.clear()


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(path))
    # Le cache PRISM aussi : jamais le vrai ~/.prism/data d'un développeur depuis un test.
    monkeypatch.setenv("PRISM_DATA_DIR", str(path / "prism"))
    return path


@pytest.fixture()
def outbox(monkeypatch):
    """Les e-mails que l'application aurait envoyés (:func:`spectre.core.email.send_email`), dans
    l'ordre - au lieu de les journaliser. Tous les appelants passent par l'attribut du module
    (``email_module.send_email``), donc le remplacer là suffit."""
    sent: list[SentEmail] = []

    def capture(to: str, subject: str, body: str) -> None:
        sent.append(SentEmail(to, subject, body))

    monkeypatch.setattr("spectre.core.email.send_email", capture)
    return sent


@pytest.fixture()
def app(data_dir):
    # Imported inside the fixture so SPECTRE_DATA_DIR is already set before spectre.core.db is
    # ever asked for a connection.
    from spectre.api.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
