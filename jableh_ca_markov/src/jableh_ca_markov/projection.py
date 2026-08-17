"""
projection.py
==============
Markov forward projection (Eq. 3) and long-run steady-state ("stationary
distribution") analysis of the estimated annual transition matrix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import linalg as la

from .config import CLASS_NAMES


def forward_projection(
    P_annual: np.ndarray,
    start_state: np.ndarray,
    start_year: int,
    horizon_years: int,
) -> pd.DataFrame:
    """
    Propagate the observed state vector forward through the annual
    transition matrix for `horizon_years` steps (Eq. 3).

    Returns a DataFrame indexed by year, one column per class, including
    the starting year's observed state as the first row.
    """
    state = np.asarray(start_state, dtype=float).copy()
    rows = {start_year: state.copy()}
    for h in range(1, horizon_years + 1):
        state = state @ P_annual
        rows[start_year + h] = state.copy()
    df = pd.DataFrame(rows, index=CLASS_NAMES).T
    df.index.name = "year"
    return df


def matrix_power_to_span(P_annual: np.ndarray, n_years: int) -> np.ndarray:
    """
    Raise the annual transition matrix to the power corresponding to an
    n-year span (e.g. n_years=11 for a 2015->2026 comparison against a
    directly cross-tabulated pixel-level matrix; see
    markov_ipf.compare_pixel_and_ipf_matrices()).
    """
    return np.linalg.matrix_power(P_annual, n_years)


def steady_state_distribution(P_annual: np.ndarray) -> np.ndarray:
    """
    Compute the stationary distribution pi satisfying pi @ P = pi,
    sum(pi) = 1 -- the left eigenvector of P_annual for eigenvalue 1.
    """
    eigvals, eigvecs = la.eig(P_annual.T)
    idx = np.argmin(np.abs(eigvals - 1.0))
    pi = np.real(eigvecs[:, idx])
    pi = np.abs(pi)
    return pi / pi.sum()


def steady_state_report(P_annual: np.ndarray, current_state: np.ndarray) -> pd.DataFrame:
    """Steady-state shares vs. current observed shares, with the gap in
    percentage points (Table `tab:steadystate` of the article)."""
    pi = steady_state_distribution(P_annual)
    total = current_state.sum()
    current_share = 100 * np.asarray(current_state) / total
    steady_share = 100 * pi
    return pd.DataFrame({
        "class": CLASS_NAMES,
        "current_share_pct": current_share,
        "steady_state_share_pct": steady_share,
        "gap_pp": steady_share - current_share,
    })
