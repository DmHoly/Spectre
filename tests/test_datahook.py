"""Le dictionnaire de hooks (spectre/core/datahook/hooks.py) - chargement des YAML, validation,
et exécution avec post-traitement. La connexion réelle à PostgreSQL (connection.run_query) est
toujours mockée ici : ces tests ne doivent jamais avoir besoin d'un réseau ou d'une base réelle.
"""

from __future__ import annotations

import pandas as pd
import pytest

from spectre.core.datahook import hooks


def test_list_hooks_finds_the_three_migrated_hooks():
    assert {"pl", "ncel", "waferlist"} <= set(hooks.list_hooks())


def test_load_hook_reads_title_description_parameters_and_sql():
    hook = hooks.load_hook("pl")
    assert hook.title == "Photoluminescence (PL)"
    assert "wafer_names" in hook.parameters
    assert "wafer_names" in hook.sql  # requête reformatée sur le nouveau nom de paramètre
    assert hook.postprocessing == ["common:add_median_per_wafer"]


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


def test_run_hook_applies_postprocessing_in_order(monkeypatch):
    def fake_run_query(sql, params):
        assert params == {"wafer_names": ["W1", "W2"]}
        return pd.DataFrame(
            {
                "Wafer name": ["W1", "W1", "W2"],
                "Dominant WL(nm)": [450.0, 452.0, 460.0],
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    df = hooks.run_hook("pl", wafer_names=["W1", "W2"])
    assert "Dominant WL(nm) médiane wafer" in df.columns
    w1_medians = df.loc[df["Wafer name"] == "W1", "Dominant WL(nm) médiane wafer"].unique()
    assert list(w1_medians) == [451.0]


def test_run_hook_with_no_postprocessing_returns_query_result_unchanged(monkeypatch):
    raw = pd.DataFrame({"wafer_name": ["A", "B"]})
    monkeypatch.setattr("spectre.core.datahook.connection.run_query", lambda sql, params: raw)
    df = hooks.run_hook("waferlist")
    pd.testing.assert_frame_equal(df, raw)
