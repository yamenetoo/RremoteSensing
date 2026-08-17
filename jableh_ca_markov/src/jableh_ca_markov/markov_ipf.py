"""
markov_ipf.py
=============
Seeded IPF/RAS transition-matrix estimation (Eqs. 1-2 of the article),
the Anderson-Goodman (1957) Markov-chain homogeneity/stationarity test,
and -- new for the revision -- direct pixel-level cross-tabulation of
two classified rasters, with a comparison utility against the
IPF/RAS-estimated matrix (revision item 2.2).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import CLASS_NAMES, N_CLASSES, YEARS


# ----------------------------------------------------------------------
# 1. Seeded IPF / RAS estimation for a single consecutive-year pair
# ----------------------------------------------------------------------
def seeded_ipf(
    area_t1: np.ndarray,
    area_t2: np.ndarray,
    seed: np.ndarray,
    max_iter: int = 500,
    tol: float = 1e-10,
    rescale_to_common_total: bool = True,
) -> np.ndarray:
    """
    Reconstruct a transition-probability matrix consistent with two
    observed marginal area vectors, using structurally-seeded Iterative
    Proportional Fitting (IPF/RAS; Deming & Stephan 1940, Wilson 1970).

    Parameters
    ----------
    area_t1, area_t2 : array-like, shape (N_CLASSES,)
        Class areas (any consistent unit, e.g. km^2) at t and t+1.
    seed : np.ndarray, shape (N_CLASSES, N_CLASSES)
        Row-stochastic seed transition-probability matrix.
    rescale_to_common_total : bool, default True
        IPF/RAS can only satisfy BOTH marginals exactly when they share
        the same total (sum(area_t1) == sum(area_t2)). With real Dynamic
        World composites this is not quite true: the number of valid
        (non-cloud-masked) pixels differs slightly between annual
        epochs (up to ~230 px / 0.02 km^2 across 2015-2026 for Jableh),
        so the two marginals differ by a small residual (~2.7e-5
        relative for a typical Jableh year-pair). Left unaddressed,
        this makes exact double-marginal convergence mathematically
        impossible and the alternating projection settles into a
        stable, non-vanishing oscillation instead of a true fixed
        point (see tests/test_markov_ipf.py for the diagnostic that
        caught this). When True (default), `area_t2` is proportionally
        rescaled to share `area_t1`'s total before fitting, which is
        standard practice for IPF with inconsistent marginal totals and
        restores exact convergence; the returned matrix is then
        renormalised by the ORIGINAL (unscaled) `area_t1`, so results
        remain expressed in the original area units.

    Returns
    -------
    np.ndarray, shape (N_CLASSES, N_CLASSES), row-stochastic.
    """
    t1 = np.asarray(area_t1, dtype=float)
    t2 = np.asarray(area_t2, dtype=float)

    if rescale_to_common_total:
        total1, total2 = t1.sum(), t2.sum()
        if total2 > 0:
            t2 = t2 * (total1 / total2)

    M = seed * t1[:, None]
    for _ in range(max_iter):
        M *= (t1 / M.sum(axis=1))[:, None]
        M *= (t2 / M.sum(axis=0))[None, :]
        # NOTE: convergence must be judged by the residual against the
        # TARGET marginals (t1, t2) directly, not by the cell-wise change
        # between consecutive full iterations. The alternating row/col
        # rescale can settle into a stable oscillation -- rows exact
        # immediately after the row-substep, then perturbed again by the
        # col-substep -- whose *net* iteration-to-iteration change shrinks
        # below a naive `tol` long before the row marginal is actually
        # converged (the loop exits mid-cycle, right after the col-
        # substep, with the row marginal still off). Checking both
        # marginal residuals explicitly avoids exiting mid-oscillation.
        row_resid = np.abs(M.sum(axis=1) - t1).max()
        col_resid = np.abs(M.sum(axis=0) - t2).max()
        if max(row_resid, col_resid) < tol:
            break
    return M / M.sum(axis=1, keepdims=True)


# ----------------------------------------------------------------------
# 2. Fit one matrix per consecutive-year pair, then average (Eq. 2)
# ----------------------------------------------------------------------
def estimate_pairwise_matrices(
    areas_by_year: dict[int, np.ndarray],
    seed: np.ndarray,
    years: list[int] | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Fit a seeded-IPF matrix for every consecutive-year pair.

    Returns
    -------
    matrices : np.ndarray, shape (n_pairs, N_CLASSES, N_CLASSES)
    labels   : list[str] of "YYYY->YYYY+1" pair labels
    """
    years = years or YEARS
    matrices, labels = [], []
    for y in years[:-1]:
        P = seeded_ipf(areas_by_year[y], areas_by_year[y + 1], seed)
        matrices.append(P)
        labels.append(f"{y}->{y + 1}")
    return np.array(matrices), labels


def average_matrix(matrices: np.ndarray) -> np.ndarray:
    """Element-wise average of pair-specific matrices, row-renormalised
    (Eq. 2). Returns the operative annual transition matrix P_annual."""
    P_avg = matrices.mean(axis=0)
    return P_avg / P_avg.sum(axis=1, keepdims=True)


def diagonal_dispersion(matrices: np.ndarray) -> pd.DataFrame:
    """Coefficient of variation of each diagonal (persistence) entry
    across the fitted pair-specific matrices -- the precision diagnostic
    reported in Section 3.2 of the article."""
    diag = matrices[:, np.arange(N_CLASSES), np.arange(N_CLASSES)]
    mean = diag.mean(axis=0)
    std = diag.std(axis=0)
    cv = np.divide(std, mean, out=np.zeros_like(std), where=mean > 1e-12)
    return pd.DataFrame({"class": CLASS_NAMES, "mean": mean, "std": std, "cv": cv})


# ----------------------------------------------------------------------
# 3. Anderson-Goodman (1957) chi-square homogeneity / stationarity test
# ----------------------------------------------------------------------
def anderson_goodman_test(
    pair_matrices: np.ndarray,
    areas_by_year: dict[int, np.ndarray],
    years: list[int] | None = None,
) -> dict:
    """
    Test H0: the transition matrices are stationary (identical) across
    the fitted periods, following the Markov-chain homogeneity framework
    of Anderson & Goodman (1957), area-weighted per period per class.

    Returns a dict with per-class and pooled chi-square statistics,
    degrees of freedom, and p-values.
    """
    years = years or YEARS
    period_years = years[:-1]
    results = []
    overall_stat, overall_df = 0.0, 0

    for i, ci in enumerate(CLASS_NAMES):
        rows, weights = [], []
        for y, P_y in zip(period_years, pair_matrices):
            rows.append(P_y[i, :])
            weights.append(areas_by_year[y][i])
        rows = np.array(rows)
        weights = np.array(weights)
        if weights.sum() < 1e-9:
            continue

        pooled = (rows * weights[:, None]).sum(axis=0) / weights.sum()
        pooled = np.clip(pooled, 1e-9, None)

        observed = rows * weights[:, None]
        expected = np.outer(weights, pooled)
        mask = expected > 1e-9
        chi2_i = float(np.sum((observed[mask] - expected[mask]) ** 2 / expected[mask]))
        df_i = max((rows.shape[0] - 1) * (int(np.sum(pooled > 1e-9)) - 1), 1)
        p_i = float(1 - stats.chi2.cdf(chi2_i, df_i))

        results.append({"class": ci, "chi2": chi2_i, "df": df_i, "p_value": p_i,
                         "stationary": p_i >= 0.05})
        overall_stat += chi2_i
        overall_df += df_i

    overall_p = float(1 - stats.chi2.cdf(overall_stat, overall_df))
    return {
        "per_class": pd.DataFrame(results),
        "pooled_chi2": overall_stat,
        "pooled_df": overall_df,
        "pooled_p": overall_p,
        "pooled_stationary": overall_p >= 0.05,
    }


# ----------------------------------------------------------------------
# 4. NEW (revision item 2.2): true pixel-level cross-tabulated matrix
# ----------------------------------------------------------------------
def pixel_level_transition_matrix(
    raster_t1: np.ndarray,
    raster_t2: np.ndarray,
    class_indices: list[int] | None = None,
    pixel_area_km2: float | None = None,
) -> dict:
    """
    Compute the DIRECT pixel-wise cross-tabulated transition matrix
    between two co-registered classified rasters (e.g. 2015 vs 2026),
    for comparison against the seeded-IPF/RAS estimate (revision item
    2.2 / Table 4 of the manuscript).

    Parameters
    ----------
    raster_t1, raster_t2 : np.ndarray, same shape
        Classified rasters (raw Dynamic World class codes) at t1 and t2.
    class_indices : list[int], optional
        Class codes to include (defaults to config.CLASS_INDICES).
    pixel_area_km2 : float, optional
        If given, also returns an area-unit (km^2) contingency table.

    Returns
    -------
    dict with:
      'counts'      : pd.DataFrame, raw pixel counts (rows=t1, cols=t2)
      'probability' : pd.DataFrame, row-normalised transition probabilities
      'area_km2'    : pd.DataFrame or None, counts converted to km^2
    """
    from .config import CLASS_INDICES as DEFAULT_CLASSES
    class_indices = class_indices or DEFAULT_CLASSES
    names = [CLASS_NAMES[DEFAULT_CLASSES.index(c)] if c in DEFAULT_CLASSES else str(c)
             for c in class_indices]

    n = len(class_indices)
    counts = np.zeros((n, n), dtype=np.int64)

    valid = np.isin(raster_t1, class_indices) & np.isin(raster_t2, class_indices)
    r1 = raster_t1[valid]
    r2 = raster_t2[valid]

    idx_map = {c: i for i, c in enumerate(class_indices)}
    for i, ci in enumerate(class_indices):
        row_mask = r1 == ci
        r2_row = r2[row_mask]
        for j, cj in enumerate(class_indices):
            counts[i, j] = np.count_nonzero(r2_row == cj)

    counts_df = pd.DataFrame(counts, index=names, columns=names)
    row_sums = counts.sum(axis=1, keepdims=True)
    row_sums_safe = np.where(row_sums == 0, 1, row_sums)
    prob_df = pd.DataFrame(counts / row_sums_safe, index=names, columns=names)

    area_df = None
    if pixel_area_km2 is not None:
        area_df = counts_df * pixel_area_km2

    return {"counts": counts_df, "probability": prob_df, "area_km2": area_df}


def compare_pixel_and_ipf_matrices(
    pixel_prob: pd.DataFrame,
    ipf_prob: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare the direct pixel-level transition matrix against the
    seeded-IPF/RAS-estimated matrix, class by class, on the diagonal
    (persistence) entries -- supports the comparison paragraph
    required by revision item 2.2.

    NOTE: `ipf_prob` here should be the matrix raised to the same time
    span as the pixel-level matrix (e.g. P_annual**11 for a 2015-2026
    comparison), not the raw annual matrix -- see
    projection.matrix_power_to_span() for the correct conversion.
    """
    names = list(pixel_prob.index)
    rows = []
    for name in names:
        p_pixel = pixel_prob.loc[name, name]
        p_ipf = ipf_prob.loc[name, name] if name in ipf_prob.index else np.nan
        rows.append({
            "class": name,
            "pixel_persistence": p_pixel,
            "ipf_persistence": p_ipf,
            "abs_difference": abs(p_pixel - p_ipf) if pd.notna(p_ipf) else np.nan,
        })
    return pd.DataFrame(rows)
