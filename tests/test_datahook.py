"""Le dictionnaire de hooks (spectre/core/datahook/hooks.py) - chargement des YAML, validation,
et exécution avec post-traitement. La connexion réelle à PostgreSQL (connection.run_query) est
toujours mockée ici : ces tests ne doivent jamais avoir besoin d'un réseau ou d'une base réelle.
"""

from __future__ import annotations

import pandas as pd
import pytest

from spectre.core.datahook import hooks
from spectre.core.datahook.postprocessing import common as pp_common


def test_list_hooks_finds_the_three_migrated_hooks():
    assert {"pl", "ncel", "waferlist"} <= set(hooks.list_hooks())


def test_load_hook_reads_title_description_parameters_and_sql():
    hook = hooks.load_hook("pl")
    assert hook.title == "Photoluminescence (PL)"
    assert "wafer_names" in hook.parameters
    assert "wafer_names" in hook.sql  # requête reformatée sur le nouveau nom de paramètre
    assert hook.postprocessing == ["pl:apply_pl_kpi"]


def test_add_median_per_wafer_generic_helper():
    df = pd.DataFrame({"wafer": ["A", "A", "B"], "value": [1.0, 3.0, 10.0]})
    out = pp_common.add_median_per_wafer(df, value_column="value", wafer_column="wafer")
    assert list(out.loc[out["wafer"] == "A", "value médiane wafer"].unique()) == [2.0]


def test_load_hook_unknown_key_raises():
    with pytest.raises(hooks.HookNotFoundError):
        hooks.load_hook("ceci_n_existe_pas")


def test_run_hook_missing_parameter_raises_before_touching_the_database(monkeypatch):
    called = False

    def fake_run_query(sql, params):
        nonlocal called
        called = True
        return pd.DataFrame()

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    with pytest.raises(hooks.HookDefinitionError):
        hooks.run_hook("pl")  # wafer_names manquant
    assert not called


def test_run_hook_applies_pl_postprocessing(monkeypatch):
    def fake_run_query(sql, params):
        assert params == {"wafer_names": ["W1"]}
        return pd.DataFrame(
            {
                "PL date": ["2026-01-01", "2026-01-02"],
                "Wafer name": ["W1", "W1"],
                "X": [1.0, 1.0],
                "Y": [1.0, 1.0],
                "Dominant WL(nm)": [450.0, 460.0],
                "Peak WL (nm)": [452.0, 462.0],
                "Integrated PL (a.u.)": [1.0, 1.1],
                "FWHM (nm)": [10.0, 11.0],
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    df = hooks.run_hook("pl", wafer_names=["W1"])
    # même point (X, Y) mesuré deux fois -> seule la mesure la plus récente (2026-01-02) survit.
    assert len(df) == 1
    assert df.iloc[0]["Dominant WL(nm)"] == 460.0


def test_run_hook_applies_ncel_postprocessing(monkeypatch):
    def fake_run_query(sql, params):
        return pd.DataFrame(
            {
                "filter": ["None", "ND1"],
                "wafer_name": ["W1", "W1"],
                "Test_Date": ["2026-01-01", "2026-01-01"],
                "x_position": [1, 2],
                "y_position": [1, 2],
                "na_current_a": ["5", "5"],
                "na_emission_max": [1.0, 1.0],
                "na_jpv_max": [1.0, 1.0],
                "na_jpv_delay": [1.0, 1.0],
                "na_time_delay": [1.0, 1.0],
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    df = hooks.run_hook("ncel", wafer_names=["W1"])
    assert len(df) == 1  # la ligne filtrée (ND1) est retirée
    assert list(df.columns) == [
        "filter",
        "wafername",
        "Test_Date",
        "X",
        "Y",
        "na_current_a",
        "na_emission_max",
        "na_jpv_max",
        "na_jpv_delay",
        "na_time_delay",
    ]


def test_run_hook_with_no_postprocessing_returns_query_result_unchanged(monkeypatch):
    raw = pd.DataFrame({"wafer_name": ["A", "B"]})
    monkeypatch.setattr("spectre.core.datahook.connection.run_query", lambda sql, params: raw)
    df = hooks.run_hook("waferlist")
    pd.testing.assert_frame_equal(df, raw)
