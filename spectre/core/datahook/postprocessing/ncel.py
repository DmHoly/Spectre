"""Post-traitement du hook ``ncel`` - repris de ``legacy/get_data.py::get_data_ncel``: ne garde
que les mesures sans filtre optique (``filter == "None"``), force le type de ``na_current_a``, et
ne garde que les colonnes utiles à l'affichage (renommées vers les noms génériques
wafername/X/Y déjà utilisés par le hook ``pl``, pour qu'un futur graphique standard puisse
traiter les deux sans cas particulier).
"""

from __future__ import annotations

import pandas as pd

_KEEP_COLUMNS = [
    "filter",
    "wafer_name",
    "Test_Date",
    "x_position",
    "y_position",
    "na_current_a",
    "na_emission_max",
    "na_jpv_max",
    "na_jpv_delay",
    "na_time_delay",
]


def apply_ncel_kpi(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["filter"] = out["filter"].astype(str)
    out = out[out["filter"] == "None"]
    out["na_current_a"] = pd.to_numeric(out["na_current_a"], errors="coerce").fillna(0).astype(int)
    out = out[[c for c in _KEEP_COLUMNS if c in out.columns]]
    out["Test_Date"] = pd.to_datetime(out["Test_Date"]).dt.date
    return out.rename(columns={"wafer_name": "wafername", "x_position": "X", "y_position": "Y"})
