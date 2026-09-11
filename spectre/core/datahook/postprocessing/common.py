"""Fonctions de post-traitement génériques (indépendantes d'un hook en particulier) - référencées
depuis un ``hook.yml`` par ``common:<nom>``. Chacune prend le DataFrame renvoyé par l'étape
précédente (la requête SQL, ou un post-traitement antérieur) et renvoie un DataFrame à son tour :
voir :func:`spectre.core.datahook.hooks.run_hook`.
"""

from __future__ import annotations

import pandas as pd


def add_median_per_wafer(df: pd.DataFrame, value_column: str = "Dominant WL(nm)", wafer_column: str = "Wafer name") -> pd.DataFrame:
    """Ajoute une colonne ``"{value_column} médiane wafer"`` : la médiane de ``value_column`` sur
    tous les points de mesure d'un même wafer, répétée sur chaque ligne de ce wafer - la valeur de
    référence qu'un graphique "médiane vs nom de wafer" (boxplot, par ex.) affiche typiquement.
    Un DataFrame qui ne porte pas ces colonnes (résultat vide, ou hook différent) est renvoyé
    inchangé plutôt que de lever une erreur - un post-traitement générique ne doit pas faire
    échouer un hook dont la forme diffère légèrement.
    """
    if value_column not in df.columns or wafer_column not in df.columns:
        return df
    out = df.copy()
    out[f"{value_column} médiane wafer"] = out.groupby(wafer_column)[value_column].transform("median")
    return out
