"""
uncertainty.py
===============
Two complementary sources of uncertainty in the 2030 projection:

1. MODEL uncertainty: bootstrap resampling of the 11 pair-specific
   transition matrices (Section 2.8 of the article).
2. DATA uncertainty (revision item 4.1, "ideal" tier): propagation of
   Dynamic World per-class classification error, by randomly
   reclassifying a percentage of pixels in each annual raster according
   to a supplied confusion matrix, then re-running the full pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CLASS_NAMES
from .markov_ipf import average_matrix
from .projection import forward_projection


# ----------------------------------------------------------------------
# 1. Model uncertainty: bootstrap over the 11 fitted transition matrices
# ----------------------------------------------------------------------
def monte_carlo_bootstrap(
    pair_matrices: np.ndarray,
    current_state: np.ndarray,
    horizon_years: int,
    n_bootstrap: int = 1000,
    random_state: int | None = 42,
) -> dict:
    """
    Resample the pair-specific transition matrices with replacement
    `n_bootstrap` times; for each replicate, average + row-renormalise,
    then project `current_state` forward `horizon_years` steps.

    Returns
    -------
    dict with 'replicates' (n_bootstrap x N_CLASSES array), 'summary'
    (DataFrame with mean / 2.5% / 97.5% per class).
    """
    rng = np.random.default_rng(random_state)
    n_pairs = pair_matrices.shape[0]
    replicates = np.zeros((n_bootstrap, len(current_state)))

    for b in range(n_bootstrap):
        idx = rng.choice(n_pairs, size=n_pairs, replace=True)
        P_boot = average_matrix(pair_matrices[idx])
        state = np.asarray(current_state, dtype=float)
        for _ in range(horizon_years):
            state = state @ P_boot
        replicates[b] = state

    summary = pd.DataFrame({
        "class": CLASS_NAMES,
        "mean": replicates.mean(axis=0),
        "ci_low_2.5pct": np.percentile(replicates, 2.5, axis=0),
        "ci_high_97.5pct": np.percentile(replicates, 97.5, axis=0),
    })
    return {"replicates": replicates, "summary": summary}


# ----------------------------------------------------------------------
# 2. Data uncertainty: classification-error perturbation (revision 4.1)
# ----------------------------------------------------------------------
def perturb_raster_by_confusion_matrix(
    raster: np.ndarray,
    confusion_matrix: pd.DataFrame,
    class_indices: list[int],
    random_state: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Randomly reclassify pixels in a single classified raster according
    to a supplied per-class confusion matrix (rows = "true" class,
    columns = probability of being labelled as each class; rows must
    sum to 1). This simulates one realisation of Dynamic World's known
    classification error for uncertainty propagation.

    IMPORTANT: `confusion_matrix` should be sourced from the actual
    Dynamic World validation results (Brown et al. 2022, supplementary
    accuracy tables) rather than assumed -- pass in the real matrix
    once available; this function only implements the perturbation
    mechanics, not the confusion-matrix values themselves.
    """
    rng = random_state or np.random.default_rng()
    perturbed = raster.copy()

    for i, true_code in enumerate(class_indices):
        mask = raster == true_code
        n_pixels = int(mask.sum())
        if n_pixels == 0:
            continue
        probs = confusion_matrix.iloc[i].values.astype(float)
        probs = probs / probs.sum()
        sampled_codes = rng.choice(class_indices, size=n_pixels, p=probs)
        perturbed[mask] = sampled_codes

    return perturbed


def bootstrap_with_perturbation(
    pair_matrices: np.ndarray,
    current_state: np.ndarray,
    horizon_years: int,
    perturbation_std_frac: float = 0.05,
    n_bootstrap: int = 100,
    random_state: int | None = 42,
) -> dict:
    """
    Approximate combined model + data uncertainty WITHOUT requiring the
    full raster-level perturbation loop (useful as a fast, area-only
    proxy): each bootstrap replicate additionally perturbs the observed
    2026 area vector itself by +/- `perturbation_std_frac` (Gaussian,
    per class), representing classification-count uncertainty, before
    projecting forward.

    For a rigorous, pixel-level version consistent with revision item
    4.1, use perturb_raster_by_confusion_matrix() inside the full
    raster pipeline (100 realisations recommended) instead.
    """
    rng = np.random.default_rng(random_state)
    n_pairs = pair_matrices.shape[0]
    state0 = np.asarray(current_state, dtype=float)
    replicates = np.zeros((n_bootstrap, len(state0)))

    for b in range(n_bootstrap):
        idx = rng.choice(n_pairs, size=n_pairs, replace=True)
        P_boot = average_matrix(pair_matrices[idx])

        noise = rng.normal(loc=1.0, scale=perturbation_std_frac, size=state0.shape)
        state = np.clip(state0 * noise, 0, None)
        state = state * (state0.sum() / state.sum())  # renormalise to conserve total area

        for _ in range(horizon_years):
            state = state @ P_boot
        replicates[b] = state

    summary = pd.DataFrame({
        "class": CLASS_NAMES,
        "mean": replicates.mean(axis=0),
        "ci_low_2.5pct": np.percentile(replicates, 2.5, axis=0),
        "ci_high_97.5pct": np.percentile(replicates, 97.5, axis=0),
    })
    return {"replicates": replicates, "summary": summary}
