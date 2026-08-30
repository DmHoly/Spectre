from __future__ import annotations

import pytest


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / "data"
    monkeypatch.setenv("SPECTRE_DATA_DIR", str(path))
    return path


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
