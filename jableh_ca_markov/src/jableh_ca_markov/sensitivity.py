"""
sensitivity.py
================
Sensitivity analyses required by the revision:

3.1 Seed-matrix sensitivity: re-run the full IPF/RAS -> Markov
    projection pipeline under three alternative seed matrices
    (optimistic / pessimistic / uniform) and compare the resulting 2030
    area projections against the original.

3.2 CA-parameter sensitivity: vary the distance-decay constant D0 and
    the local-density kernel window size, and report the resulting
    2030 built-up area, patch count, and mean patch size.

Item 3.1 only needs the area time series (fully computable here). Item
3.2 needs the real pixel-level CA allocation loop and is therefore
provided as a runnable function that expects real raster inputs from
the caller (see docstring).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CLASS_NAMES, N_CLASSES, YEARS, build_seed_matrix
from .markov_ipf import estimate_pairwise_matrices, average_matrix
from .projection import forward_projection


# ----------------------------------------------------------------------
# 3.1 Seed-matrix sensitivity (fully self-contained: area data only)
# ----------------------------------------------------------------------
def seed_matrix_variants() -> dict[str, np.ndarray]:
    """
    Three alternative seed matrices, as specified in the revision:
      - optimistic : uniform high persistence (0.90) for every class
      - pessimistic: low persistence for forest/crops (0.70), high for
                     built (0.95)
      - uniform    : every cell = 1/N_CLASSES (maximum-entropy / no prior)

    Returns a dict {"original": ..., "optimistic": ..., "pessimistic": ...,
    "uniform": ...} of row-stochastic (N_CLASSES x N_CLASSES) matrices.
    """
    original = build_seed_matrix()

    optimistic_persist = {c: 0.90 for c in CLASS_NAMES}
    optimistic = build_seed_matrix(persist=optimistic_persist)

    pessimistic_persist = {
        "trees": 0.70, "crops": 0.70, "built": 0.95,
        "grass": 0.5, "shrub": 0.6, "bare": 0.4,
    }
    pessimistic = build_seed_matrix(persist=pessimistic_persist)

    uniform = np.full((N_CLASSES, N_CLASSES), 1.0 / N_CLASSES)

    return {
        "original": original,
        "optimistic": optimistic,
        "pessimistic": pessimistic,
        "uniform": uniform,
    }


def run_seed_sensitivity(
    areas_by_year: dict[int, np.ndarray],
    horizon_years: int = 4,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """
    For each of the four seed variants (original + 3 alternatives), fit
    P_annual from the full area time series and project forward to the
    target horizon. Returns a comparison table of 2030 (or
    start_year+horizon) areas per class per seed.
    """
    years = years or YEARS
    variants = seed_matrix_variants()
    last_year = years[-1]
    target_year = last_year + horizon_years

    rows = []
    for name, seed in variants.items():
        pair_matrices, _ = estimate_pairwise_matrices(areas_by_year, seed, years=years)
        P_annual = average_matrix(pair_matrices)
        proj = forward_projection(P_annual, areas_by_year[last_year], last_year, horizon_years)
        target_row = proj.loc[target_year]
        row = {"seed": name}
        row.update({cls: target_row[cls] for cls in CLASS_NAMES})
        rows.append(row)

    df = pd.DataFrame(rows).set_index("seed")

    # Robustness summary: range (max - min) across seeds per class
    ranges = df.max() - df.min()
    df.loc["range_across_seeds"] = ranges
    return df


# ----------------------------------------------------------------------
# 3.2 CA-parameter sensitivity (requires real raster pipeline)
# ----------------------------------------------------------------------
def run_ca_parameter_sensitivity(
    ca_allocation_fn,
    lulc_base: np.ndarray,
    built_targets_by_year: dict[int, float],
    pixel_area_km2: float,
    pixel_size_m: float,
    conv_to_built: np.ndarray,
    d0_values: list[float] = (300.0, 500.0, 800.0),
    window_values: list[int] = (3, 5, 7),
    class_indices: list[int] | None = None,
) -> pd.DataFrame:
    """
    Run the CA allocation for every (D0, window) combination (9 runs by
    default) and report the resulting 2030 built-up area, patch count,
    and mean patch size.

    Requires `ca_allocation_fn` (typically ca_allocation.run_ca_allocation)
    bound to real raster inputs -- this function is a thin sweep wrapper
    and cannot itself synthesise meaningful raster data.
    """
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover
        raise ImportError("scipy is required for patch statistics") from exc

    results = []
    for D0 in d0_values:
        for window in window_values:
            out = ca_allocation_fn(
                lulc_base=lulc_base,
                built_targets_by_year=built_targets_by_year,
                pixel_area_km2=pixel_area_km2,
                pixel_size_m=pixel_size_m,
                conv_to_built=conv_to_built,
                D0=D0,
                window=window,
                class_indices=class_indices,
            )
            built_mask = (out["final_lulc"] == class_indices[-2]).astype(np.uint8) \
                if class_indices else (out["final_lulc"] == 6).astype(np.uint8)

            labeled, n_patches = ndimage.label(built_mask)
            patch_sizes = ndimage.sum(built_mask, labeled, range(1, n_patches + 1))

            results.append({
                "D0_m": D0,
                "window": window,
                "built_area_km2": float(built_mask.sum() * pixel_area_km2),
                "n_patches": int(n_patches),
                "mean_patch_size_px": float(np.mean(patch_sizes)) if n_patches else np.nan,
            })

    return pd.DataFrame(results)
