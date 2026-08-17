"""
pipeline.py
============
End-to-end orchestration of the full Jableh CA-Markov workflow.

`run_statistical_pipeline()` requires ONLY the annual area time series
(e.g. loaded from Pivot_km2.csv) and runs entirely offline: transition
matrix estimation, stationarity test, forward projection, steady-state,
Monte Carlo bootstrap, seed-matrix sensitivity, and the forest-
protection policy scenario. This is the part fully exercised by
tests/test_pipeline.py.

`run_full_pipeline()` additionally requires Google Earth Engine
credentials and the real Jableh raster stack (pixel-level transition
matrix, CA allocation with slope/road, direction/hotspot analysis,
hindcasting, green-belt scenario, benchmark models, cartographic maps)
and is intended to run in Colab.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from . import config
from .config import CLASS_NAMES, YEARS, build_seed_matrix
from .markov_ipf import estimate_pairwise_matrices, average_matrix, diagonal_dispersion, anderson_goodman_test
from .projection import forward_projection, steady_state_report
from .uncertainty import monte_carlo_bootstrap
from .sensitivity import run_seed_sensitivity
from .scenarios import run_forest_protection_scenario


def load_pivot_csv(pivot_csv_path: str) -> dict[int, np.ndarray]:
    """Load Pivot_km2.csv (year x class area table) into the
    {year: np.ndarray} format expected by every function in this package."""
    df = pd.read_csv(pivot_csv_path, index_col=0)
    df = df[CLASS_NAMES] if all(c in df.columns for c in CLASS_NAMES) else df
    return {int(year): df.loc[year, CLASS_NAMES].values.astype(float) for year in df.index}


def run_statistical_pipeline(
    areas_by_year: dict[int, np.ndarray],
    horizon_years: int = 4,
    n_bootstrap: int = 1000,
    output_dir: str | None = None,
) -> dict:
    """
    Run every area-based (offline, no-raster-required) analysis step:
      1. Seeded IPF/RAS transition-matrix estimation (all 11 pairs)
      2. Diagonal dispersion diagnostic
      3. Anderson-Goodman stationarity test
      4. Markov forward projection to `horizon_years` ahead
      5. Steady-state distribution report
      6. Monte Carlo bootstrap uncertainty on the projection
      7. Seed-matrix sensitivity comparison
      8. Forest-protection policy scenario projection

    Returns a dict of all intermediate and final results. If
    `output_dir` is given, also writes every table to CSV there.
    """
    seed = build_seed_matrix()
    years = sorted(areas_by_year)
    last_year = years[-1]

    pair_matrices, pair_labels = estimate_pairwise_matrices(areas_by_year, seed, years=years)
    P_annual = average_matrix(pair_matrices)
    dispersion = diagonal_dispersion(pair_matrices)
    stationarity = anderson_goodman_test(pair_matrices, areas_by_year, years=years)

    projection = forward_projection(P_annual, areas_by_year[last_year], last_year, horizon_years)
    steady_state = steady_state_report(P_annual, areas_by_year[last_year])

    mc = monte_carlo_bootstrap(pair_matrices, areas_by_year[last_year], horizon_years, n_bootstrap)

    seed_sensitivity = run_seed_sensitivity(areas_by_year, horizon_years, years=years)

    forest_protection = run_forest_protection_scenario(
        P_annual, areas_by_year[last_year], last_year, horizon_years, new_trees_to_built=0.01,
    )

    results = {
        "P_annual": P_annual,
        "pair_matrices": pair_matrices,
        "pair_labels": pair_labels,
        "dispersion": dispersion,
        "stationarity": stationarity,
        "projection": projection,
        "steady_state": steady_state,
        "monte_carlo_summary": mc["summary"],
        "seed_sensitivity": seed_sensitivity,
        "forest_protection_projection": forest_protection,
    }

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(P_annual, index=CLASS_NAMES, columns=CLASS_NAMES).to_csv(out / "P_annual.csv")
        dispersion.to_csv(out / "diagonal_dispersion.csv", index=False)
        stationarity["per_class"].to_csv(out / "stationarity_per_class.csv", index=False)
        projection.to_csv(out / "markov_projection.csv")
        steady_state.to_csv(out / "steady_state.csv", index=False)
        mc["summary"].to_csv(out / "monte_carlo_summary.csv", index=False)
        seed_sensitivity.to_csv(out / "seed_sensitivity.csv")
        forest_protection.to_csv(out / "forest_protection_projection.csv")

    return results


def run_full_pipeline(base_dir: str, path_overrides: dict | None = None) -> dict:
    """
    Full raster-dependent pipeline (data download, PNG export, pixel-
    level transition matrix, CA allocation with slope/road, direction/
    hotspot analysis, hindcasting, benchmark models, cartographic maps).

    This function documents and wires together every module but is
    intended to be run inside Colab with GEE credentials and the real
    Jableh raster stack already present under `base_dir` -- it cannot
    execute meaningfully offline. See notebooks/01_full_pipeline.ipynb
    for the runnable, cell-by-cell version with the exact GEE/Drive
    setup calls.
    """
    raise NotImplementedError(
        "run_full_pipeline() requires Google Earth Engine credentials and "
        "the real Jableh raster stack; run notebooks/01_full_pipeline.ipynb "
        "in Colab instead, or call the individual raster-dependent functions "
        "in ca_allocation.py / spatial_analysis.py / validation.py / "
        "mapping.py directly with your own loaded raster arrays."
    )
