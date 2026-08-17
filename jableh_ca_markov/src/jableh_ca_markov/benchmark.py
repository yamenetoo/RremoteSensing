"""
benchmark.py
=============
Alternative, more "black-box" suitability models for comparison against
the rule-based CA suitability surface (revision item 3.3):

  - Logistic-regression CA: fit a logistic regression on distance-to-
    built, slope, and road-distance predictors using pixels that did /
    did not convert to built-up between 2015-2026 as the training
    labels; use the predicted probability surface as the CA suitability.

  - A thin wrapper for an equivalent simple ANN (MLPClassifier) is also
    provided for the same comparison, since the revision explicitly
    allows "Logistic Regression or ANN".

Both require real predictor rasters (distance/slope/road) and the
actual 2015 vs 2026 change labels -- they are written to run directly
against the project's raster stack but cannot produce meaningful output
without it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sample_training_pixels(
    changed_to_built_mask: np.ndarray,
    candidate_mask: np.ndarray,
    n_samples_per_class: int | None = None,
    random_state: int = 42,
) -> np.ndarray:
    """
    Sample a balanced set of pixel indices: 50% that changed to built
    (2015->2026) and 50% that did not, drawn from `candidate_mask`
    (typically "was not already built in 2015").

    Returns a boolean sample mask, same shape as the inputs.
    """
    rng = np.random.default_rng(random_state)

    changed_idx = np.flatnonzero(changed_to_built_mask & candidate_mask)
    unchanged_idx = np.flatnonzero((~changed_to_built_mask) & candidate_mask)

    n = n_samples_per_class or min(len(changed_idx), len(unchanged_idx))
    n = min(n, len(changed_idx), len(unchanged_idx))

    sampled_changed = rng.choice(changed_idx, size=n, replace=False)
    sampled_unchanged = rng.choice(unchanged_idx, size=n, replace=False)

    sample_mask = np.zeros(changed_to_built_mask.size, dtype=bool)
    sample_mask[sampled_changed] = True
    sample_mask[sampled_unchanged] = True
    return sample_mask.reshape(changed_to_built_mask.shape)


def fit_logistic_ca(
    predictors: dict[str, np.ndarray],
    changed_to_built_mask: np.ndarray,
    candidate_mask: np.ndarray,
    n_samples_per_class: int | None = None,
    random_state: int = 42,
):
    """
    Fit a logistic regression predicting P(convert to built) from the
    given predictor rasters (e.g. {'dist_built': ..., 'slope': ...,
    'dist_road': ...}), then return the fitted model plus a full-extent
    suitability surface (predicted probability for every pixel).

    Requires scikit-learn.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sample_mask = sample_training_pixels(
        changed_to_built_mask, candidate_mask, n_samples_per_class, random_state,
    )

    names = list(predictors.keys())
    X_train = np.column_stack([predictors[k][sample_mask] for k in names])
    y_train = changed_to_built_mask[sample_mask].astype(int)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    model = LogisticRegression(max_iter=1000, random_state=random_state)
    model.fit(X_train_scaled, y_train)

    full_shape = changed_to_built_mask.shape
    X_full = np.column_stack([predictors[k].ravel() for k in names])
    X_full_scaled = scaler.transform(X_full)
    proba = model.predict_proba(X_full_scaled)[:, 1].reshape(full_shape)

    return {"model": model, "scaler": scaler, "predictor_names": names, "suitability": proba}


def fit_ann_ca(
    predictors: dict[str, np.ndarray],
    changed_to_built_mask: np.ndarray,
    candidate_mask: np.ndarray,
    hidden_layer_sizes: tuple = (16, 8),
    n_samples_per_class: int | None = None,
    random_state: int = 42,
):
    """Simple MLP (ANN) equivalent of fit_logistic_ca(), for the "or ANN"
    alternative mentioned in the revision. Requires scikit-learn."""
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    sample_mask = sample_training_pixels(
        changed_to_built_mask, candidate_mask, n_samples_per_class, random_state,
    )

    names = list(predictors.keys())
    X_train = np.column_stack([predictors[k][sample_mask] for k in names])
    y_train = changed_to_built_mask[sample_mask].astype(int)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    model = MLPClassifier(hidden_layer_sizes=hidden_layer_sizes, max_iter=2000,
                            random_state=random_state)
    model.fit(X_train_scaled, y_train)

    full_shape = changed_to_built_mask.shape
    X_full = np.column_stack([predictors[k].ravel() for k in names])
    X_full_scaled = scaler.transform(X_full)
    proba = model.predict_proba(X_full_scaled)[:, 1].reshape(full_shape)

    return {"model": model, "scaler": scaler, "predictor_names": names, "suitability": proba}


def compare_models(validation_reports: dict[str, pd.DataFrame], built_2030_km2: dict[str, float]) -> pd.DataFrame:
    """
    Assemble the final benchmark-comparison table: average Kappa / FoM
    (from each model's hindcasting validation_report DataFrame) plus
    each model's 2030 built-up projection.

    `validation_reports` : {"Our CA": df, "Logistic-CA": df, "ANN-CA": df}
      where each df is the output of validation.run_hindcast() (must
      contain an "Average" row with 'kappa' and 'FoM' columns).
    `built_2030_km2` : {"Our CA": 57.43, "Logistic-CA": ..., "ANN-CA": ...}
    """
    rows = []
    for name, df in validation_reports.items():
        avg_row = df.loc["Average"]
        rows.append({
            "model": name,
            "avg_kappa_2023_2026": avg_row.get("kappa", np.nan),
            "avg_FoM": avg_row.get("FoM", np.nan),
            "built_2030_km2": built_2030_km2.get(name, np.nan),
        })
    return pd.DataFrame(rows).set_index("model")
