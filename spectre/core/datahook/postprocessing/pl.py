"""Post-traitement du hook ``pl`` - repris de ``legacy/get_data.py::get_pl_eta`` (la logique de
départ, avant reformatage) : borne la longueur d'onde dominante à une plage exploitable, ne garde
que la mesure la plus récente par point (un wafer peut être mesuré plusieurs fois), reprojette
chaque point sur son "champ" (une zone du wafer, voir ``_field_index``) plutôt que ses coordonnées
brutes, puis moyenne les mesures d'un même champ. ``legacy/wafermap.py::WaferMap.get_field`` fait
la même chose mais importe ``matplotlib`` juste pour son usage de tracé annexe (``.plot()``) -
inutile ici, donc reproduit en pur calcul plutôt que d'ajouter cette dépendance pour une fonction.
"""

from __future__ import annotations

import math

import pandas as pd

FIELD_WIDTH_MM = 20.0
FIELD_HEIGHT_MM = 9.0


def _field_index(x: float, y: float, field_width: float = FIELD_WIDTH_MM, field_height: float = FIELD_HEIGHT_MM) -> tuple[int, int]:
    """Le champ (i, j) contenant (x, y), le champ (0, 0) étant centré sur (0, 0) - voir
    ``legacy/wafermap.py::WaferMap.get_field``.
    """
    i = math.floor((x + field_width / 2) / field_width)
    j = math.floor((y + field_height / 2) / field_height)
    return int(i), int(j)


def apply_pl_kpi(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[(df["Dominant WL(nm)"] >= 440) & (df["Dominant WL(nm)"] <= 700)]
    out = out.sort_values(by=["Wafer name", "X", "Y", "PL date"], ascending=[True, True, True, False])
    out = out.drop_duplicates(subset=["Wafer name", "X", "Y"], keep="first")

    fields = out.apply(lambda row: _field_index(row["X"], row["Y"]), axis=1)
    out = out.assign(
        x_coord=out["X"],
        y_coord=out["Y"],
        X=[f[0] for f in fields],
        Y=[f[1] + 1 for f in fields],
        wafername=out["Wafer name"],
    )

    return (
        out.groupby(["X", "Y", "wafername"])
        .agg(
            {
                "Dominant WL(nm)": "mean",
                "Peak WL (nm)": "mean",
                "Integrated PL (a.u.)": "mean",
                "FWHM (nm)": "mean",
                "x_coord": "mean",
                "y_coord": "mean",
            }
        )
        .reset_index()
    )
