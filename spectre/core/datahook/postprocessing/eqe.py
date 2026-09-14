"""Post-traitement du hook ``eqe`` (EQE/LIV) - repris de ``legacy/get_data.py::get_liv`` et des
petits calculs de ``legacy/liv_kpi_calculation.py`` (regroupés ici, un seul module, plutôt que
réimporter tel quel ce fichier legacy) : à partir d'un balayage I-V-EQE-spectre brut par device, en
tire les grandeurs qu'on compare habituellement d'un device/wafer à l'autre (EQE max, tension et
courant à EQE max, longueur d'onde/pureté au point de fonctionnement, rendement d'allumage par
wafer, densité de courant, KPI à 25 A/cm²...). ``ciexy_to_hex`` vient de
``legacy/color_kpi_calculation.py`` - portée seule ici plutôt que le fichier entier, qui charge par
ailleurs un fichier ressource (le locus spectral) absent de ce dépôt et inutilisé par ce calcul.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_float_array(data):
    if np.isscalar(data):
        return np.array([float("nan") if data is None else float(data)])
    return np.array(pd.to_numeric(pd.Series(data), errors="coerce"))


def get_max_EQE(EQE):
    eqe_array = _to_float_array(EQE)
    if eqe_array.size == 0 or np.all(np.isnan(eqe_array)):
        return np.nan
    return float(np.nanmax(eqe_array))


def get_V_at_max_EQE(V, EQE):
    eqe_max = get_max_EQE(EQE)
    if np.isnan(eqe_max):
        return np.nan, np.nan
    eqe_array = _to_float_array(EQE)
    v_array = _to_float_array(V)
    if np.all(np.isnan(eqe_array)):
        return np.nan, np.nan
    idx_max = np.nanargmax(eqe_array)
    return v_array[idx_max], idx_max


def get_I_at_max_EQE(I, EQE):
    eqe_max = get_max_EQE(EQE)
    if np.isnan(eqe_max):
        return np.nan, np.nan
    eqe_array = _to_float_array(EQE)
    i_array = _to_float_array(I)
    if np.all(np.isnan(eqe_array)):
        return np.nan, np.nan
    idx_max = np.nanargmax(eqe_array)
    return i_array[idx_max], idx_max


def get_max_wl(row):
    spectra = row["Spectra"]
    wl = row["Wavelength"]
    idx_at_max_eqe = row["Idx at Max EQE"]
    if idx_at_max_eqe is not None and not np.isnan(idx_at_max_eqe):
        idx_at_max_eqe = int(idx_at_max_eqe)
        spectrum = spectra[idx_at_max_eqe]
        if isinstance(spectrum, (list, np.ndarray)) and len(spectrum) > 0:
            idx_max = np.nanargmax(spectrum)
            return wl[int(idx_max)]
    return np.nan


def get_current_at_voltage(row, voltage):
    V_array = _to_float_array(row["V"])
    current_array = _to_float_array(row["I"])
    if V_array.size == 0 or current_array.size == 0 or np.all(np.isnan(V_array)) or np.all(np.isnan(current_array)):
        return np.nan
    mask = ~np.isnan(V_array) & ~np.isnan(current_array)
    if np.sum(mask) < 2:
        return np.nan
    return float(np.interp(voltage, V_array[mask], current_array[mask]))


def get_lambda_dom_at_max_EQE(Lambda_Dominant, EQE):
    eqe_array = _to_float_array(EQE)
    ld_array = _to_float_array(Lambda_Dominant)
    if np.all(np.isnan(eqe_array)):
        return np.nan
    idx_max = np.nanargmax(eqe_array)
    if idx_max >= len(ld_array):
        return np.nan
    return float(ld_array[idx_max])


def get_purity_at_max_EQE(Purity, EQE):
    eqe_array = _to_float_array(EQE)
    purity_array = _to_float_array(Purity)
    if np.all(np.isnan(eqe_array)):
        return np.nan
    idx_max = np.nanargmax(eqe_array)
    if idx_max >= len(purity_array):
        return np.nan
    return float(purity_array[idx_max])


def is_lit(EQE, threshold=1e-6):
    arr = _to_float_array(EQE)
    valid = arr[~np.isnan(arr)]
    if len(valid) == 0:
        return False
    return bool(np.any(valid > threshold))


def compute_spectral_kpis_for_row(wavelengths, spectra_list):
    """Lambda_peak et FWHM pour chaque spectre d'une ligne (un spectre par point I-V du balayage).
    Renvoie deux listes de même longueur que ``spectra_list``.
    """
    if spectra_list is None or wavelengths is None:
        return [], []
    wavelengths = np.array(wavelengths)
    lambda_peaks, fwhms = [], []
    for intensity in spectra_list:
        arr = np.array(intensity, dtype=float)
        if arr.sum() == 0 or np.all(arr == 0):
            lambda_peaks.append(np.nan)
            fwhms.append(np.nan)
            continue
        peak_idx = np.argmax(arr)
        lambda_peak = wavelengths[peak_idx]
        try:
            half_max = arr[peak_idx] / 2.0
            left_indices = np.where((wavelengths < lambda_peak) & (arr < half_max))[0]
            right_indices = np.where((wavelengths > lambda_peak) & (arr < half_max))[0]
            if len(left_indices) == 0 or len(right_indices) == 0:
                fwhm = np.nan
            else:
                i_l = left_indices[-1]
                x_left = np.interp(half_max, [arr[i_l], arr[i_l + 1]], [wavelengths[i_l], wavelengths[i_l + 1]])
                i_r = right_indices[0]
                x_right = np.interp(half_max, [arr[i_r], arr[i_r - 1]], [wavelengths[i_r], wavelengths[i_r - 1]])
                fwhm = x_right - x_left
        except Exception:
            fwhm = np.nan
        lambda_peaks.append(lambda_peak)
        fwhms.append(fwhm)
    return lambda_peaks, fwhms


def _get_scalar_at_max_eqe(vec, eqe_vec):
    if vec is None or eqe_vec is None:
        return np.nan
    try:
        idx = int(np.argmax(eqe_vec))
        return vec[idx]
    except Exception:
        return np.nan


def ciexy_to_hex(x, y, Y=1.0):
    """CIE 1931 (x, y) -> couleur sRGB affichable, en hex - reprise telle quelle de
    ``legacy/color_kpi_calculation.py::ciexy_to_hex``."""
    if y == 0:
        return "#000000"
    X = (x * Y) / y
    Z = ((1 - x - y) * Y) / y
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    rgb = np.array([r, g, b])
    rgb = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(np.maximum(rgb, 0), 1 / 2.4) - 0.055)
    rgb = np.clip(rgb, 0, 1)
    rgb255 = (rgb * 255).astype(int)
    return "#{:02X}{:02X}{:02X}".format(*rgb255)


def downsample_spectra(df: pd.DataFrame, n: int = 100) -> pd.DataFrame:
    """Réduit la taille des vecteurs ``Wavelength``/``Spectra`` à ~``n`` points par sous-
    échantillonnage régulier (garde 1 point sur ``len(Wavelength) // n``) - un spectre mesuré a
    souvent plusieurs centaines de points, inutiles une fois ``Lambda_Peak``/``FWHM`` déjà extraits
    par :func:`compute_spectral_kpis_for_row` (appliqué avant cette étape dans
    :func:`apply_eqe_kpi`) : n'allège que ce qui est stocké/transporté/mis en cache, pas les KPI
    scalaires qui en ont déjà été tirés à pleine résolution.
    """
    if df.empty or "Wavelength" not in df.columns or "Spectra" not in df.columns:
        return df

    def _downsample_row(row):
        wavelengths = row["Wavelength"]
        spectra = row["Spectra"]
        if wavelengths is None or len(wavelengths) == 0:
            return pd.Series({"Wavelength": wavelengths, "Spectra": spectra})
        step = max(1, len(wavelengths) // n)
        return pd.Series(
            {
                "Wavelength": wavelengths[::step],
                "Spectra": [s[::step] for s in spectra] if spectra is not None else spectra,
            }
        )

    out = df.copy()
    out[["Wavelength", "Spectra"]] = out.apply(_downsample_row, axis=1)
    return out


def apply_eqe_kpi(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.dropna(how="all")
    if out.empty:
        return out

    out["max_EQE"] = out["EQE"].apply(get_max_EQE)
    out[["V at Max EQE", "Idx at Max EQE"]] = out.apply(lambda row: pd.Series(get_V_at_max_EQE(row["V"], row["EQE"])), axis=1)
    out["I at Max EQE"] = out.apply(lambda row: get_I_at_max_EQE(row["I"], row["EQE"])[0], axis=1)
    out["Wavelength at Max EQE"] = out.apply(get_max_wl, axis=1)
    out["current_2.3V"] = out.apply(lambda row: get_current_at_voltage(row, 2.3), axis=1)
    out["current_-5V"] = out.apply(lambda row: get_current_at_voltage(row, -5.0), axis=1)
    out["current_10V"] = out.apply(lambda row: get_current_at_voltage(row, 10.0), axis=1)
    out["Test_Date"] = pd.to_datetime(out["Test_Date"]).dt.date
    out["Lambda_Dom_at_MaxEQE"] = out.apply(lambda row: get_lambda_dom_at_max_EQE(row["Lambda_Dominant"], row["EQE"]), axis=1)
    out["Purity_at_MaxEQE"] = out.apply(lambda row: get_purity_at_max_EQE(row["Purity"], row["EQE"]), axis=1)
    out["Purity_at_MaxEQE"] = out["Purity_at_MaxEQE"].apply(lambda x: round(x, 2) if pd.notna(x) else x)
    out["is_lit"] = out["EQE"].apply(is_lit)

    # Yield par wafer - % de LEDs allumées dans le même wafer.
    out["yield_per_wafer"] = out.groupby("wafer_name")["is_lit"].transform(lambda x: round(x.sum() / len(x) * 100, 1))

    out = out.rename(columns={"Block_Y_Coordinate": "Y", "Block_X_Coordinate": "X", "wafer_name": "wafername"})

    out[["size_x_um", "size_y_um"]] = out["Led_Name"].str.extract(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)").astype(float)
    multiplier = out["Led_Name"].str.extract(r"\d+(?:\.\d+)?x\d+(?:\.\d+)?-(\d+)")[0].astype(float).fillna(1)
    out["area_cm2"] = out["size_x_um"] * out["size_y_um"] * multiplier * 1e-8

    out["srgb"] = out.apply(
        lambda row: [
            ciexy_to_hex(x, y) if pd.notna(x) and pd.notna(y) else "#808080" for x, y in zip(row["CIEx"], row["CIEy"])
        ]
        if row["CIEx"] is not None and row["CIEy"] is not None
        else [],
        axis=1,
    )

    out["J"] = out.apply(lambda row: [np.abs(i) / row["area_cm2"] for i in row["I"]] if row["I"] is not None else [], axis=1)
    out["J_at_MaxEQE"] = np.abs(out["I at Max EQE"]) / out["area_cm2"]

    out["EQE_25A_cm2"] = out.apply(
        lambda row: np.interp(25, row["J"], row["EQE"]) if row["J"] is not None and len(row["J"]) > 1 and row["EQE"] is not None else np.nan,
        axis=1,
    )
    out["V_25A_cm2"] = out.apply(
        lambda row: np.interp(25, row["J"], row["V"]) if row["J"] is not None and len(row["J"]) > 1 and row["V"] is not None else np.nan,
        axis=1,
    )
    out["Lambda_Dom_25A_cm2"] = out.apply(
        lambda row: np.interp(25, row["J"], row["Lambda_Dominant"])
        if row["J"] is not None and len(row["J"]) > 1 and row["Lambda_Dominant"] is not None
        else np.nan,
        axis=1,
    )

    for v_label, col in [("2.3V", "current_2.3V"), ("-5V", "current_-5V"), ("10V", "current_10V")]:
        out[f"J_at_{v_label}"] = (np.abs(out[col]) / out["area_cm2"]).apply(lambda x: round(x, 2) if pd.notna(x) else x)

    out["max_EQE_reached"] = out.apply(lambda row: False if row["EQE"] is None or row["max_EQE"] == row["EQE"][-1] else True, axis=1)

    out[["Lambda_Peak", "FWHM"]] = pd.DataFrame(
        [compute_spectral_kpis_for_row(row["Wavelength"], row["Spectra"]) for _, row in out.iterrows()],
        columns=["Lambda_Peak", "FWHM"],
        index=out.index,
    )
    out["Lambda_Peak_at_MaxEQE"] = out.apply(lambda row: _get_scalar_at_max_eqe(row["Lambda_Peak"], row["EQE"]), axis=1)
    out["FWHM_at_MaxEQE"] = out.apply(lambda row: _get_scalar_at_max_eqe(row["FWHM"], row["EQE"]), axis=1)
    out["Lambda_Peak_25A_cm2"] = out.apply(
        lambda row: np.interp(25, row["J"], row["Lambda_Peak"])
        if row["J"] is not None and len(row["J"]) > 1 and row["Lambda_Peak"] is not None
        else np.nan,
        axis=1,
    )
    out["FWHM_25A_cm2"] = out.apply(
        lambda row: np.interp(25, row["J"], row["FWHM"]) if row["J"] is not None and len(row["J"]) > 1 and row["FWHM"] is not None else np.nan,
        axis=1,
    )

    columns_to_keep = [
        "wafername", "X", "Y", "Test_Date", "Led_Name", "CIEx", "CIEy", "I", "V", "L", "EQE", "Wavelength", "Spectra",
        "Lambda_Dominant", "Purity", "max_EQE", "V at Max EQE", "I at Max EQE", "current_2.3V", "current_-5V",
        "current_10V", "Lambda_Dom_at_MaxEQE", "Purity_at_MaxEQE", "is_lit", "yield_per_wafer",
        "size_x_um", "size_y_um", "area_cm2", "srgb", "J", "J_at_MaxEQE", "EQE_25A_cm2", "V_25A_cm2", "Lambda_Dom_25A_cm2",
        "J_at_2.3V", "J_at_-5V", "J_at_10V", "max_EQE_reached", "Lambda_Peak", "FWHM",
        "Lambda_Peak_at_MaxEQE", "FWHM_at_MaxEQE", "Lambda_Peak_25A_cm2", "FWHM_25A_cm2", "Optical_Sensor",
    ]
    return out[[c for c in columns_to_keep if c in out.columns]]
