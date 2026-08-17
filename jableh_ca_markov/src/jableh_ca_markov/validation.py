"""
validation.py
==============
Accuracy-assessment metrics (Overall Accuracy, Kappa and its Location /
Quantity variants, Figure of Merit) and the retrospective hindcasting
workflow required by revision item 2.1: recalibrate on 2015-2022,
simulate 2023-2026, and compare against the actually observed rasters
for those years.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HINDCAST_CALIBRATION_YEARS, HINDCAST_VALIDATION_YEARS


# ----------------------------------------------------------------------
# Accuracy metrics
# ----------------------------------------------------------------------
def overall_accuracy(simulated: np.ndarray, observed: np.ndarray) -> float:
    """Fraction of pixels where simulated == observed."""
    valid = ~(np.isnan(simulated) | np.isnan(observed)) if simulated.dtype.kind == "f" else np.ones_like(simulated, dtype=bool)
    return float(np.mean(simulated[valid] == observed[valid]))


def kappa_coefficient(simulated: np.ndarray, observed: np.ndarray, class_indices: list[int]) -> dict:
    """
    Standard Cohen's Kappa plus the location/quantity decomposition
    commonly reported in CA-Markov validation studies (Pontius 2000,
    Mondal et al. 2016).

    Returns dict with 'kappa_standard', 'kappa_location', 'kappa_quantity'.
    """
    n = len(class_indices)
    conf = np.zeros((n, n), dtype=np.int64)
    for i, ci in enumerate(class_indices):
        mask_i = observed == ci
        for j, cj in enumerate(class_indices):
            conf[i, j] = np.count_nonzero(mask_i & (simulated == cj))

    total = conf.sum()
    po = np.trace(conf) / total  # observed agreement (= overall accuracy)

    row_marg = conf.sum(axis=1) / total
    col_marg = conf.sum(axis=0) / total
    pe = float(np.sum(row_marg * col_marg))  # expected agreement by chance

    kappa_standard = (po - pe) / (1 - pe) if (1 - pe) > 0 else np.nan

    # Kappa for location: agreement given the correct overall quantity
    # (max possible agreement under the observed marginals)
    max_agreement = np.sum(np.minimum(row_marg, col_marg))
    kappa_location = (po - pe) / (max_agreement - pe) if (max_agreement - pe) > 0 else np.nan

    # Kappa for quantity: how well the SIMULATED class totals match the
    # OBSERVED class totals, ignoring spatial location entirely
    pmax = max_agreement
    kappa_quantity = (pmax - pe) / (1 - pe) if (1 - pe) > 0 else np.nan

    return {
        "confusion_matrix": conf,
        "overall_accuracy": float(po),
        "kappa_standard": float(kappa_standard),
        "kappa_location": float(kappa_location),
        "kappa_quantity": float(kappa_quantity),
    }


def figure_of_merit(simulated: np.ndarray, observed: np.ndarray, baseline: np.ndarray) -> float:
    """
    Figure of Merit (FoM) = hits / (hits + misses + false_alarms), where
    change is defined relative to `baseline` (the pre-period map).
    hits            = pixels correctly predicted to change AND to the
                       correct class
    misses          = pixels that changed in reality but the model
                       predicted no change (or wrong class)
    false_alarms    = pixels the model predicted would change but did
                       not change in reality (or changed to a different
                       class than predicted)
    """
    obs_changed = observed != baseline
    sim_changed = simulated != baseline

    hits = np.count_nonzero(obs_changed & sim_changed & (simulated == observed))
    misses = np.count_nonzero(obs_changed & ~(sim_changed & (simulated == observed)))
    false_alarms = np.count_nonzero(sim_changed & ~obs_changed)

    denom = hits + misses + false_alarms
    return float(hits / denom) if denom > 0 else np.nan


def validation_report(simulated: np.ndarray, observed: np.ndarray, baseline: np.ndarray,
                        class_indices: list[int]) -> dict:
    """Bundle OA / Kappa variants / FoM into a single report dict for one
    validation year."""
    k = kappa_coefficient(simulated, observed, class_indices)
    fom = figure_of_merit(simulated, observed, baseline)
    return {
        "OA_pct": 100 * k["overall_accuracy"],
        "kappa": k["kappa_standard"],
        "kappa_location": k["kappa_location"],
        "kappa_quantity": k["kappa_quantity"],
        "FoM": fom,
    }


# ----------------------------------------------------------------------
# Retrospective hindcasting workflow (revision item 2.1)
# ----------------------------------------------------------------------
def run_hindcast(
    areas_by_year: dict[int, np.ndarray],
    observed_rasters_by_year: dict[int, np.ndarray],
    lulc_2022: np.ndarray,
    class_indices: list[int],
    seed_matrix,
    calibration_years: list[int] | None = None,
    validation_years: list[int] | None = None,
    ca_allocation_fn=None,
    ca_allocation_kwargs: dict | None = None,
) -> pd.DataFrame:
    """
    Full hindcasting workflow:
      1. Re-fit P_annual using ONLY the calibration-period area pairs
         (2015-2022 by default).
      2. Forward-project from the 2022 observed state to each
         validation year (2023-2026).
      3. Run the CA allocation (via `ca_allocation_fn`, typically
         ca_allocation.run_ca_allocation) to produce a simulated raster
         for each validation year, starting from `lulc_2022`.
      4. Compare each simulated raster against the actually observed
         raster for that year via validation_report().

    Returns a DataFrame with one row per validation year (OA, Kappa
    variants, FoM) plus an "Average" summary row.

    NOTE: this function orchestrates the workflow but delegates the
    actual pixel-level simulation to `ca_allocation_fn`, which the
    caller must supply (bound to the real Jableh raster stack) -- it
    cannot be executed against synthetic data alone in a way that
    produces meaningful accuracy numbers, only against genuine rasters.
    """
    from .markov_ipf import estimate_pairwise_matrices, average_matrix
    from .projection import forward_projection

    calibration_years = calibration_years or HINDCAST_CALIBRATION_YEARS
    validation_years = validation_years or HINDCAST_VALIDATION_YEARS

    calib_areas = {y: areas_by_year[y] for y in calibration_years}
    pair_matrices, _ = estimate_pairwise_matrices(calib_areas, seed_matrix, years=calibration_years)
    P_calib = average_matrix(pair_matrices)

    last_calib_year = calibration_years[-1]
    proj = forward_projection(P_calib, areas_by_year[last_calib_year], last_calib_year,
                                horizon_years=len(validation_years))

    rows = []
    lulc_current = lulc_2022
    for h, year in enumerate(validation_years, start=1):
        if ca_allocation_fn is None:
            rows.append({"year": year, "OA_pct": np.nan, "kappa": np.nan,
                         "kappa_location": np.nan, "kappa_quantity": np.nan, "FoM": np.nan,
                         "note": "ca_allocation_fn not supplied -- pixel simulation skipped"})
            continue

        target_built_km2 = float(proj.loc[year, "built"])
        result = ca_allocation_fn(
            lulc_base=lulc_current,
            built_targets_by_year={year: target_built_km2},
            **(ca_allocation_kwargs or {}),
        )
        simulated = result["final_lulc"]
        observed = observed_rasters_by_year[year]

        report = validation_report(simulated, observed, baseline=lulc_2022, class_indices=class_indices)
        report["year"] = year
        rows.append(report)
        lulc_current = simulated  # roll forward for next validation year

    df = pd.DataFrame(rows).set_index("year")
    numeric_cols = [c for c in df.columns if c != "note"]
    df.loc["Average"] = df[numeric_cols].mean()
    return df
