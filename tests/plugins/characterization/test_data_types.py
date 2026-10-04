"""L'API /api/characterization - les types de données de caractérisation, servis par PRISM (paquet
``prism-aledia-datahook``) ou par la démo (``SPECTRE_DEMO_DATA=1``). La logique des hooks (YAML,
post-traitements KPI, cache) est testée dans PRISM lui-même ; ici on vérifie ce que Spectre ajoute :
l'authentification, la forme JSON renvoyée à la page /donnees, la vérification des paramètres, et la
traduction des erreurs PRISM en codes HTTP lisibles - et que la démo tient le même contrat.

L'accès base de PRISM (``prism.connections.run_query``) est toujours mocké : ces tests ne doivent
jamais avoir besoin d'un réseau ni d'une configuration ~/.prism.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import prism
import pytest

from spectre.plugins.characterization import service
from spectre.plugins.characterization.demo import GENERATORS
from spectre.plugins.characterization.source import json_safe
from support.accounts import signup
from support.characterization import get_chart, get_data_type, list_categories, list_data_types, run_query
from support.http import assert_handler_404, assert_ok


@pytest.fixture()
def logged_in(client):
    signup(client, "data@example.com", name="Data")
    return client


@pytest.fixture()
def demo_data(monkeypatch):
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")


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


def _never_query(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("cette requête ne devait jamais atteindre la base")

    monkeypatch.setattr("prism.connections.run_query", fail_if_called)


def test_characterization_requires_login(client):
    assert client.get("/api/characterization/data-types").status_code == 401


def test_list_exposes_the_prism_catalogue_in_light_form(logged_in):
    data_types = list_data_types(logged_in)
    keys = {t["key"] for t in data_types}
    assert {"pl", "ncel", "waferlist", "eqe"} <= keys
    assert keys == set(prism.list_hooks())
    pl = next(t for t in data_types if t["key"] == "pl")
    assert pl == {
        "key": "pl",
        "title": "Photoluminescence (PL)",
        "description": pl["description"],
        "category": "Post EPI",
        "status": "implemented",
        "by_wafer": True,
        "representative_column": pl["representative_column"],
    }


def test_list_filters_by_status_wafer_and_category(logged_in):
    by_wafer = list_data_types(logged_in, status="implemented", by_wafer=True)
    assert {t["key"] for t in by_wafer} >= {"pl", "ncel", "eqe"}
    assert all(t["status"] == "implemented" and t["by_wafer"] for t in by_wafer)
    assert "waferlist" not in {t["key"] for t in by_wafer}  # implémenté, mais sans plaque
    assert "tem" not in {t["key"] for t in by_wafer}  # fiche documentaire
    planned = list_data_types(logged_in, status="planned")
    assert planned and all(t["status"] == "planned" for t in planned)
    post_epi = list_data_types(logged_in, category="Post EPI")
    assert "pl" in {t["key"] for t in post_epi} and all(t["category"] == "Post EPI" for t in post_epi)
    assert logged_in.get("/api/characterization/data-types", params={"status": "inconnu"}).status_code == 422


def test_detail_carries_wiki_fields_including_formula_and_chart_urls(logged_in):
    data_type = assert_ok(get_data_type(logged_in, "pl"))
    assert data_type["title"] == "Photoluminescence (PL)"
    assert data_type["category"] == "Post EPI"
    assert data_type["cacheable"] is True and data_type["by_wafer"] is True
    assert data_type["parameters"] == ["wafer_names"]
    column = data_type["raw_columns"][0]
    assert {"name", "description", "example", "source", "formula", "unit"} <= set(column)
    eqe = assert_ok(get_data_type(logged_in, "eqe"))
    chart = eqe["charts"][0]
    assert chart["url"] == f"/api/characterization/data-types/eqe/charts/{chart['key']}"


def test_categories_group_implemented_and_planned_types(logged_in):
    categories = {c["name"]: c["data_types"] for c in list_categories(logged_in)}
    assert any(t["status"] == "planned" for types in categories.values() for t in types)
    assert "pl" in {t["key"] for t in categories["Post EPI"]}


def test_unknown_type_is_404(logged_in):
    assert_handler_404(get_data_type(logged_in, "ceci_n_existe_pas"), "type de données inconnu")
    assert_handler_404(run_query(logged_in, "ceci_n_existe_pas"), "type de données inconnu")
    assert_handler_404(get_chart(logged_in, "ceci_n_existe_pas", "x"), "type de données inconnu")


def test_an_invalid_hook_yml_is_left_out_of_the_catalogue_and_logged(logged_in, tmp_path, monkeypatch, caplog):
    installed = prism.settings.hooks_dir()
    hooks = tmp_path / "hooks"
    for key in ("pl", "tem"):
        shutil.copytree(installed / key, hooks / key)
    (hooks / "broken").mkdir()
    (hooks / "broken" / "hook.yml").write_text("description: sans titre\n", encoding="utf-8")
    monkeypatch.setenv("PRISM_HOOKS_DIR", str(hooks))

    with caplog.at_level(logging.WARNING, logger="spectre.plugins.characterization"):
        categories = list_categories(logged_in)
    assert {t["key"] for c in categories for t in c["data_types"]} == {"pl", "tem"}
    assert any("broken" in record.getMessage() for record in caplog.records)
    assert {t["key"] for t in list_data_types(logged_in)} == {"pl", "tem"}
    # la fiche elle-même n'est pas « introuvable » : PRISM la sert mal
    response = get_data_type(logged_in, "broken")
    assert response.status_code == 502 and "invalide" in response.json()["detail"]


def test_query_uses_prism_cache(logged_in, data_dir, monkeypatch):
    calls = []

    def fake_run_query(sql, params, profile=None):
        calls.append(list(params["wafer_names"]))
        return _fake_pl_rows(list(params["wafer_names"]))

    monkeypatch.setattr("prism.connections.run_query", fake_run_query)

    first = assert_ok(run_query(logged_in, "pl", {"wafer_names": ["W1"]}))
    assert first["fetched"] == ["W1"] and first["from_cache"] == []
    assert first["row_count"] == 1 and first["source"] == "prism"

    second = assert_ok(run_query(logged_in, "pl", {"wafer_names": [" W1 ", "W2", "W2", ""]}))
    assert second["from_cache"] == ["W1"] and second["fetched"] == ["W2"]
    assert second["wafers"] == ["W1", "W2"]  # nettoyées, sans doublon
    assert calls == [["W1"], ["W2"]]
    # Le cache PRISM est rangé dans le dossier de données de Spectre, pas dans ~/.prism.
    assert (data_dir / "prism" / "hook_cache" / "pl").is_dir()

    refreshed = assert_ok(run_query(logged_in, "pl", {"wafer_names": ["W1"]}, refresh=True))
    assert refreshed["from_cache"] == [] and refreshed["fetched"] == ["W1"]


def test_query_cells_are_json_safe(logged_in, monkeypatch):
    def rows_with_holes(sql, params, profile=None):
        return pd.DataFrame(
            {
                "wafer_name": ["W1", "W2"],
                "value": [np.nan, np.inf],
                "spectrum": [np.array([1.0, np.nan]), np.array([-np.inf, 2.0])],
                "measured_at": [pd.Timestamp("2026-01-02"), pd.NaT],
            }
        )

    monkeypatch.setattr("prism.connections.run_query", rows_with_holes)
    result = assert_ok(run_query(logged_in, "waferlist"))
    assert result["from_cache"] is None and result["fetched"] is None  # type non mis en cache
    assert result["rows"] == [
        ["W1", None, [1.0, None], "2026-01-02T00:00:00"],
        ["W2", None, [None, 2.0], None],
    ]


def test_json_safe_converts_without_changing_the_shape():
    assert json_safe(float("nan")) is None
    assert json_safe(float("-inf")) is None
    assert json_safe(np.float32("nan")) is None
    assert json_safe(np.int64(3)) == 3 and type(json_safe(np.int64(3))) is int
    assert json_safe(np.array([[1, 2], [3, np.nan]])) == [[1, 2], [3, None]]
    assert json_safe({"a": (np.inf, "x")}) == {"a": [None, "x"]}
    assert json_safe(pd.NaT) is None and json_safe(None) is None
    assert json_safe("texte") == "texte"


def test_query_parameters_are_checked_before_reaching_the_database(logged_in, monkeypatch):
    _never_query(monkeypatch)
    assert run_query(logged_in, "pl").status_code == 422  # paramètre manquant
    assert run_query(logged_in, "pl", {"wafer_names": [" ", ""]}).status_code == 422  # aucune plaque
    too_many = [f"W{n}" for n in range(service.MAX_WAFERS + 1)]
    response = run_query(logged_in, "pl", {"wafer_names": too_many})
    assert response.status_code == 422 and str(service.MAX_WAFERS) in response.json()["detail"]
    shape = logged_in.post("/api/characterization/data-types/pl/queries", json={"parameters": {"wafer_names": "W1"}})
    assert shape.status_code == 422


def test_query_on_a_planned_type_is_422(logged_in, monkeypatch):
    _never_query(monkeypatch)
    response = run_query(logged_in, "tem")
    assert response.status_code == 422 and response.json()["code"] == "not_implemented"


def test_missing_connection_config_is_503(logged_in, monkeypatch):
    def no_config(sql, params, profile=None):
        raise prism.ConfigError("aucun fichier de profils de connexion")

    monkeypatch.setattr("prism.connections.run_query", no_config)
    response = run_query(logged_in, "waferlist")
    assert response.status_code == 503
    assert "configuration de connexion" in response.json()["detail"]


@pytest.mark.parametrize("error", [prism.ConnectionFailed("connexion impossible au profil 'carac'"), prism.QueryFailed("syntaxe")])
def test_database_failure_is_502(logged_in, monkeypatch, error):
    def unreachable(sql, params, profile=None):
        raise error

    monkeypatch.setattr("prism.connections.run_query", unreachable)
    response = run_query(logged_in, "waferlist")
    assert response.status_code == 502 and "la requête PRISM a échoué" in response.json()["detail"]


def test_chart_renders_png_without_touching_the_database(logged_in, monkeypatch):
    _never_query(monkeypatch)
    chart = assert_ok(get_data_type(logged_in, "eqe"))["charts"][0]
    response = logged_in.get(chart["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert_handler_404(get_chart(logged_in, "eqe", "inconnu"), "graphique inconnu")


def test_the_source_is_chosen_from_the_demo_setting(monkeypatch):
    assert service.current_source().name == "prism"
    monkeypatch.setenv("SPECTRE_DEMO_DATA", "1")
    assert service.current_source().name == "demo"


def test_demo_lists_only_what_it_can_serve(logged_in, demo_data):
    keys = {t["key"] for t in list_data_types(logged_in)}
    assert keys == set(GENERATORS)
    served = {t["key"] for c in list_categories(logged_in) for t in c["data_types"]}
    assert served == set(GENERATORS)
    assert list_data_types(logged_in, status="planned") == []


def test_demo_answers_like_prism(logged_in, demo_data, monkeypatch):
    _never_query(monkeypatch)
    # un type qu'elle ne sert pas : 404, comme un type inconnu de PRISM
    for key in ("tem", "ceci_n_existe_pas"):
        assert_handler_404(get_data_type(logged_in, key), "type de données inconnu")
        assert_handler_404(run_query(logged_in, key), "type de données inconnu")
    assert run_query(logged_in, "eqe", {"wafer_names": []}).status_code == 422
    too_many = [f"W{n}" for n in range(service.MAX_WAFERS + 1)]
    assert run_query(logged_in, "eqe", {"wafer_names": too_many}).status_code == 422

    result = assert_ok(run_query(logged_in, "eqe", {"wafer_names": ["W12-A3"]}))
    assert result["source"] == "demo" and result["wafers"] == ["W12-A3"]
    assert {"wafername", "max_EQE", "I", "EQE"} <= set(result["columns"])
    assert assert_ok(run_query(logged_in, "eqe", {"wafer_names": ["W12-A3"]}))["rows"] == result["rows"]
    assert assert_ok(run_query(logged_in, "waferlist"))["row_count"] > 0

    detail = assert_ok(get_data_type(logged_in, "eqe"))
    assert detail["status"] == "implemented"
    assert logged_in.get(detail["charts"][0]["url"]).headers["content-type"] == "image/png"


def test_a_single_adapter_imports_prism():
    root = Path(__file__).resolve().parents[3] / "spectre"
    pattern = re.compile(r"^\s*(import prism\b|from prism\b)", re.MULTILINE)
    importing = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py") if pattern.search(path.read_text(encoding="utf-8")))
    assert importing == ["plugins/characterization/prism_source.py"]
