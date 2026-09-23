"""L'API /api/donnees - l'adaptateur HTTP de Spectre au-dessus de PRISM (paquet
``prism-aledia-datahook``). La logique des hooks (YAML, post-traitements KPI, cache) est testée dans
PRISM lui-même ; ici on vérifie seulement ce que Spectre ajoute : l'authentification, la forme JSON
renvoyée à la page /donnees, et la traduction des erreurs PRISM en codes HTTP lisibles.

L'accès base de PRISM (``prism.connections.run_query``) est toujours mocké : ces tests ne doivent
jamais avoir besoin d'un réseau ni d'une configuration ~/.prism.
"""

from __future__ import annotations

import pandas as pd
import prism
import pytest


@pytest.fixture()
def logged_in(client):
    client.post("/api/auth/register", json={"email": "data@example.com", "password": "supersecret", "name": "Data"})
    return client


def _fake_pl_rows(wafer_names):
    n = len(wafer_names)
    return pd.DataFrame(
        {
            "wafername": wafer_names,
            "Wafer name": wafer_names,
            "X": [1.0] * n,
            "Y": [1.0] * n,
            "PL date": ["2026-01-01"] * n,
            "Dominant WL(nm)": [450.0] * n,
            "Peak WL (nm)": [452.0] * n,
            "Integrated PL (a.u.)": [1.0] * n,
            "FWHM (nm)": [10.0] * n,
        }
    )


def test_donnees_requires_login(client):
    assert client.get("/api/donnees/hooks").status_code == 401


def test_list_hooks_exposes_the_prism_catalogue(logged_in):
    response = logged_in.get("/api/donnees/hooks")
    assert response.status_code == 200
    keys = {h["key"] for h in response.json()["hooks"]}
    assert {"pl", "ncel", "waferlist", "eqe"} <= keys
    assert keys == set(prism.list_hooks())


def test_hook_summary_carries_wiki_fields_including_formula(logged_in):
    hook = logged_in.get("/api/donnees/hooks/pl").json()
    assert hook["title"] == "Photoluminescence (PL)"
    assert hook["category"] == "Post EPI"
    assert hook["cacheable"] is True
    column = hook["raw_columns"][0]
    assert {"name", "description", "example", "source", "formula", "unit"} <= set(column)


def test_categories_group_implemented_and_planned_hooks(logged_in):
    categories = {c["name"]: c["hooks"] for c in logged_in.get("/api/donnees/categories").json()["categories"]}
    assert any(h["status"] == "planned" for hooks in categories.values() for h in hooks)


def test_unknown_hook_is_404(logged_in):
    assert logged_in.get("/api/donnees/hooks/ceci_n_existe_pas").status_code == 404


def test_run_hook_uses_prism_cache(logged_in, data_dir, monkeypatch):
    calls = []

    def fake_run_query(sql, params, profile=None):
        calls.append(list(params["wafer_names"]))
        return _fake_pl_rows(list(params["wafer_names"]))

    monkeypatch.setattr("prism.connections.run_query", fake_run_query)

    first = logged_in.post("/api/donnees/hooks/pl/executer", json={"parameters": {"wafer_names": ["W1"]}}).json()
    assert first["fetched"] == ["W1"] and first["from_cache"] == []
    assert first["row_count"] == 1

    second = logged_in.post("/api/donnees/hooks/pl/executer", json={"parameters": {"wafer_names": ["W1", "W2"]}}).json()
    assert second["from_cache"] == ["W1"] and second["fetched"] == ["W2"]
    assert calls == [["W1"], ["W2"]]
    # Le cache PRISM est rangé dans le dossier de données de Spectre, pas dans ~/.prism.
    assert (data_dir / "prism" / "hook_cache" / "pl").is_dir()


def test_run_hook_missing_parameter_is_422(logged_in):
    assert logged_in.post("/api/donnees/hooks/pl/executer", json={"parameters": {}}).status_code == 422


def test_run_planned_hook_is_422(logged_in):
    assert logged_in.post("/api/donnees/hooks/tem/executer", json={"parameters": {}}).status_code == 422


def test_missing_connection_config_is_400(logged_in, monkeypatch):
    def no_config(sql, params, profile=None):
        raise prism.ConfigError("aucun fichier de profils de connexion")

    monkeypatch.setattr("prism.connections.run_query", no_config)
    response = logged_in.post("/api/donnees/hooks/waferlist/executer", json={"parameters": {}})
    assert response.status_code == 400
    assert "configuration de connexion" in response.json()["detail"]


def test_database_failure_is_502(logged_in, monkeypatch):
    def unreachable(sql, params, profile=None):
        raise prism.ConnectionFailed("connexion impossible au profil 'carac'")

    monkeypatch.setattr("prism.connections.run_query", unreachable)
    response = logged_in.post("/api/donnees/hooks/waferlist/executer", json={"parameters": {}})
    assert response.status_code == 502


def test_chart_renders_png_without_touching_the_database(logged_in, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("un graphique de fiche ne doit jamais requêter la base")

    monkeypatch.setattr("prism.connections.run_query", fail_if_called)
    chart_key = logged_in.get("/api/donnees/hooks/eqe").json()["charts"][0]["key"]
    response = logged_in.get(f"/api/donnees/hooks/eqe/graphiques/{chart_key}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
