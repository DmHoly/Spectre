"""Graphiques pédagogiques pour le hook ``eqe`` (I-V-EQE-spectre)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from . import common

_Q = 1.602176634e-19  # charge élémentaire (C)
_K = 1.380649e-23  # constante de Boltzmann (J/K)
_T = 300.0  # température supposée (K) - pas mesurée par ce hook, approximation ambiante


def iv_curve_with_extraction(df: pd.DataFrame) -> Figure:
    """Courbe I-V du premier device de la sélection, avec l'ajustement qui sert à en extraire deux
    grandeurs qu'on ne lit pas directement dans le tableau de KPI :

    - le **facteur d'idéalité** n : pente de ln(I) vs V dans la zone exponentielle de la diode
      (ni trop bas - bruit de fond - ni trop haut - déjà limité par la résistance série), via
      n = q / (kT * pente) ;
    - la **résistance série** Rs : pente de V vs I en haute injection, où la caractéristique devient
      linéaire (c'est la méthode la plus simple d'extraction de Rs - il en existe de plus robustes,
      ex. Cheung, mais celle-ci suffit à illustrer le principe visuellement).

    Ce ne sont ni des KPI stockés ni recalculés par ``postprocessing/eqe.py`` : ce graphique existe
    justement pour montrer *comment* on les lirait sur la courbe, une donnée que le tableau seul ne
    montre pas. Les bornes des deux zones (25-60e centile pour n, 15 derniers % pour Rs) sont des
    heuristiques simples, pas une méthode de caractérisation validée en labo.
    """
    if df.empty:
        return common.empty_figure("Aucune donnée pour ce wafer/device.")

    row = df.iloc[0]
    V = np.asarray(row.get("V"), dtype=float) if row.get("V") is not None else np.array([])
    I = np.asarray(row.get("I"), dtype=float) if row.get("I") is not None else np.array([])
    if V.size == 0 or I.size == 0 or V.size != I.size:
        return common.empty_figure("Pas de vecteur I/V exploitable sur cette ligne.")

    mask = (V > 0) & (I > 0)
    V, I = V[mask], I[mask]
    order = np.argsort(V)
    V, I = V[order], I[order]
    if V.size < 6:
        return common.empty_figure("Pas assez de points en polarisation directe pour extraire n / Rs.")

    fig = Figure(figsize=(10, 4.2))
    ax_n, ax_rs = fig.subplots(1, 2)

    # -- facteur d'idéalité : ln(I) vs V, zone médiane -------------------------------------------
    ax_n.semilogy(V, I, "o", ms=3, color="#2a6f77", label="mesure")
    lo, hi = int(V.size * 0.25), int(V.size * 0.6)
    if hi - lo >= 3:
        Vf, lnI = V[lo:hi], np.log(I[lo:hi])
        slope, intercept = np.polyfit(Vf, lnI, 1)
        n = _Q / (_K * _T * slope) if slope > 0 else float("nan")
        fit_V = np.linspace(Vf[0], Vf[-1], 20)
        label = f"ajustement (n ≈ {n:.2f})" if n == n else "ajustement"
        ax_n.semilogy(fit_V, np.exp(intercept + slope * fit_V), "--", color="#c0392b", label=label)
    ax_n.set_xlabel("V (V)")
    ax_n.set_ylabel("I (A)")
    ax_n.set_title("Facteur d'idéalité\n(pente de ln I vs V, zone exponentielle)", fontsize=10)
    ax_n.legend(fontsize=8)

    # -- résistance série : V vs I, haute injection ----------------------------------------------
    ax_rs.plot(I, V, "o", ms=3, color="#2a6f77", label="mesure")
    lo_rs = int(V.size * 0.85)
    if V.size - lo_rs >= 3:
        Ir, Vr = I[lo_rs:], V[lo_rs:]
        slope_rs, intercept_rs = np.polyfit(Ir, Vr, 1)
        fit_I = np.linspace(Ir[0], Ir[-1], 20)
        ax_rs.plot(fit_I, intercept_rs + slope_rs * fit_I, "--", color="#c0392b", label=f"ajustement (Rs ≈ {slope_rs * 1000:.1f} mΩ)")
    ax_rs.set_xlabel("I (A)")
    ax_rs.set_ylabel("V (V)")
    ax_rs.set_title("Résistance série\n(pente de V vs I, haute injection)", fontsize=10)
    ax_rs.legend(fontsize=8)

    device = row.get("Led_Name", "")
    fig.suptitle(f"Courbe I-V — {device}" if device else "Courbe I-V", fontsize=11)
    fig.tight_layout()
    return fig
