"""Le dictionnaire de hooks (spectre/core/datahook/hooks.py) - chargement des YAML, validation,
et exécution avec post-traitement. La connexion réelle à PostgreSQL (connection.run_query) est
toujours mockée ici : ces tests ne doivent jamais avoir besoin d'un réseau ou d'une base réelle.
"""

from __future__ import annotations

import pandas as pd
import pytest

from spectre.core.datahook import cache, hooks
from spectre.core.datahook.postprocessing import common as pp_common
from spectre.core.datahook.postprocessing import eqe as pp_eqe


def test_list_hooks_finds_the_migrated_hooks():
    assert {"pl", "ncel", "waferlist", "eqe"} <= set(hooks.list_hooks())


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


def test_load_hook_reads_wiki_metadata():
    hook = hooks.load_hook("pl")
    assert hook.category == "Post EPI"
    assert hook.status == "implemented"
    assert hook.representative_column == "Dominant WL(nm)"
    assert len(hook.raw_columns) > 0
    assert len(hook.kpi_columns) > 0
    assert len(hook.example_rows) > 0
    col = next(c for c in hook.raw_columns if c.name == "Wafer name")
    assert col.description
    assert col.example == "16J5A426MMD4"
    kpi_col = next(c for c in hook.kpi_columns if c.name == "Dominant WL(nm)")
    assert kpi_col.source == "pl:apply_pl_kpi"


def test_planned_hook_has_no_sql_and_is_not_runnable():
    hook = hooks.load_hook("tem")
    assert hook.status == "planned"
    assert hook.category == "Structure"
    assert hook.sql == ""
    with pytest.raises(hooks.HookDefinitionError):
        # query.sql absent - une tentative d'exécution doit échouer proprement, pas planter sur
        # une requête vide envoyée telle quelle à psycopg2.
        hooks.run_hook("tem")


def test_list_hooks_by_category_groups_implemented_and_planned_hooks():
    grouped = hooks.list_hooks_by_category()
    assert {h.key for h in grouped["Post EPI"]} >= {"pl", "ncel", "eqe", "pdpl", "cathodo"}
    assert {h.key for h in grouped["Structure"]} >= {"tem", "fib", "meb_g4", "sem101"}
    assert {h.key for h in grouped["Post Process"]} >= {"el", "el_pattern"}
    assert {h.key for h in grouped["Défectivité"]} >= {"defect_images", "defect_counting"}
    # un hook "planned" n'a pas de requête réelle - jamais montré comme exécutable.
    planned = [h for h in grouped["Structure"] if h.key == "tem"][0]
    assert planned.status == "planned"


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


def test_run_hook_applies_eqe_postprocessing(monkeypatch):
    def fake_run_query(sql, params):
        return pd.DataFrame(
            {
                "wafer_name": ["W1"],
                "X": [1],
                "Y": [1],
                "Led_Name": ["20x20-1"],
                "Test_Date": ["2026-01-01"],
                "I": [[-5.0, 0.0, 10.0]],
                "V": [[-5.0, 2.3, 10.0]],
                "L": [[0.0, 1.0, 2.0]],
                "EQE": [[0.01, 0.05, 0.02]],
                "Wavelength": [[400.0, 410.0, 420.0]],
                "Spectra": [[[0.0, 1.0, 0.0], [0.0, 2.0, 0.0], [0.0, 1.5, 0.0]]],
                "Lambda_Dominant": [[450.0, 452.0, 451.0]],
                "Purity": [[0.9, 0.91, 0.92]],
                "CIEx": [[0.3, 0.31, 0.32]],
                "CIEy": [[0.3, 0.31, 0.32]],
                "Optical_Sensor": ["sensor1"],
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    df = hooks.run_hook("eqe", wafer_names=["W1"])
    assert len(df) == 1
    row = df.iloc[0]
    assert row["wafername"] == "W1"
    assert row["max_EQE"] == 0.05
    assert row["is_lit"] is True or row["is_lit"] == True  # noqa: E712 (numpy bool)
    assert row["yield_per_wafer"] == 100.0
    assert row["size_x_um"] == 20.0 and row["size_y_um"] == 20.0
    assert row["area_cm2"] > 0
    # le hook applique aussi eqe:downsample_spectra (voir hooks/eqe/hook.yml) - le spectre
    # d'entrée (3 points) est déjà sous n=100, donc inchangé ; testé pour de vrai ci-dessous.
    assert len(row["Wavelength"]) == 3


def test_downsample_spectra_keeps_roughly_n_points():
    wavelengths = list(range(1000))
    spectra = [[float(i) for i in range(1000)], [float(i) * 2 for i in range(1000)]]
    df = pd.DataFrame({"Wavelength": [wavelengths], "Spectra": [spectra]})
    out = pp_eqe.downsample_spectra(df, n=100)
    assert 90 <= len(out.iloc[0]["Wavelength"]) <= 110
    assert all(len(s) == len(out.iloc[0]["Wavelength"]) for s in out.iloc[0]["Spectra"])


def test_downsample_spectra_ignores_short_spectra():
    df = pd.DataFrame({"Wavelength": [[1.0, 2.0, 3.0]], "Spectra": [[[1.0, 2.0, 3.0]]]})
    out = pp_eqe.downsample_spectra(df, n=100)
    assert list(out.iloc[0]["Wavelength"]) == [1.0, 2.0, 3.0]


def test_downsample_spectra_noop_when_columns_missing():
    df = pd.DataFrame({"other": [1, 2]})
    out = pp_eqe.downsample_spectra(df, n=100)
    pd.testing.assert_frame_equal(out, df)


def test_cache_round_trip(data_dir):
    rows = [{"wafername": "W1", "value": 1.0}, {"wafername": "W1", "value": 2.0}]
    assert cache.read_cached_rows("pl", "W1") is None
    cache.write_cache("pl", "W1", rows)
    assert cache.read_cached_rows("pl", "W1") == rows


def test_cache_is_isolated_per_hook_and_per_wafer(data_dir):
    cache.write_cache("pl", "W1", [{"a": 1}])
    cache.write_cache("ncel", "W1", [{"a": 2}])
    cache.write_cache("pl", "W2", [{"a": 3}])
    assert cache.read_cached_rows("pl", "W1") == [{"a": 1}]
    assert cache.read_cached_rows("ncel", "W1") == [{"a": 2}]
    assert cache.read_cached_rows("pl", "W2") == [{"a": 3}]


def test_clear_cache_one_wafer_or_whole_hook(data_dir):
    cache.write_cache("pl", "W1", [{"a": 1}])
    cache.write_cache("pl", "W2", [{"a": 2}])
    cache.clear_cache("pl", "W1")
    assert cache.read_cached_rows("pl", "W1") is None
    assert cache.read_cached_rows("pl", "W2") is not None
    cache.clear_cache("pl")
    assert cache.read_cached_rows("pl", "W2") is None


def test_run_hook_cached_only_queries_missing_wafers(data_dir, monkeypatch):
    calls = []

    def fake_run_query(sql, params):
        calls.append(list(params["wafer_names"]))
        return pd.DataFrame(
            {
                "wafername": params["wafer_names"],
                "Wafer name": params["wafer_names"],
                "X": [1.0] * len(params["wafer_names"]),
                "Y": [1.0] * len(params["wafer_names"]),
                "PL date": ["2026-01-01"] * len(params["wafer_names"]),
                "Dominant WL(nm)": [450.0] * len(params["wafer_names"]),
                "Peak WL (nm)": [452.0] * len(params["wafer_names"]),
                "Integrated PL (a.u.)": [1.0] * len(params["wafer_names"]),
                "FWHM (nm)": [10.0] * len(params["wafer_names"]),
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)

    result = hooks.run_hook_cached("pl", ["W1", "W2"])
    assert calls == [["W1", "W2"]]  # rien en cache -> les deux wafers requêtés
    assert sorted(result.fetched) == ["W1", "W2"]
    assert result.from_cache == []
    assert len(result.df) == 2

    calls.clear()
    result2 = hooks.run_hook_cached("pl", ["W1", "W2", "W3"])
    assert calls == [["W3"]]  # W1/W2 déjà en cache, seul W3 est requêté
    assert sorted(result2.from_cache) == ["W1", "W2"]
    assert result2.fetched == ["W3"]
    assert len(result2.df) == 3


def test_run_hook_cached_refresh_forces_requery(data_dir, monkeypatch):
    calls = []

    def fake_run_query(sql, params):
        calls.append(list(params["wafer_names"]))
        return pd.DataFrame(
            {
                "wafername": params["wafer_names"],
                "Wafer name": params["wafer_names"],
                "X": [1.0],
                "Y": [1.0],
                "PL date": ["2026-01-01"],
                "Dominant WL(nm)": [450.0],
                "Peak WL (nm)": [452.0],
                "Integrated PL (a.u.)": [1.0],
                "FWHM (nm)": [10.0],
            }
        )

    monkeypatch.setattr("spectre.core.datahook.connection.run_query", fake_run_query)
    hooks.run_hook_cached("pl", ["W1"])
    calls.clear()
    hooks.run_hook_cached("pl", ["W1"], refresh=True)
    assert calls == [["W1"]]  # refresh=True ignore le cache existant


def test_run_hook_cached_falls_back_for_non_cacheable_hook(data_dir, monkeypatch):
    raw = pd.DataFrame({"wafer_name": ["A", "B"]})
    monkeypatch.setattr("spectre.core.datahook.connection.run_query", lambda sql, params: raw)
    result = hooks.run_hook_cached("waferlist", [])
    pd.testing.assert_frame_equal(result.df, raw)


def test_run_hook_with_no_postprocessing_returns_query_result_unchanged(monkeypatch):
    raw = pd.DataFrame({"wafer_name": ["A", "B"]})
    monkeypatch.setattr("spectre.core.datahook.connection.run_query", lambda sql, params: raw)
    df = hooks.run_hook("waferlist")
    pd.testing.assert_frame_equal(df, raw)
