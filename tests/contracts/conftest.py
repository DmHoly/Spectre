from __future__ import annotations

import pytest


@pytest.fixture()
def app(data_dir, monkeypatch):
    """L'application avec tous ses plugins, ceux qu'une variable active compris (kpis_demo :
    ``SPECTRE_DEMO_DATA=1``) : le front qui appelle leurs routes ou charge leurs fichiers est vérifié
    comme le reste."""
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    from spectre.kernel.app import create_app

    return create_app()
