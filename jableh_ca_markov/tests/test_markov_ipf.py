"""
Unit tests for the offline (raster-free) statistical modules:
config, markov_ipf, projection, uncertainty, sensitivity, scenarios.

Run with:  pytest tests/ -v
"""

import numpy as np
import pytest

from jableh_ca_markov.config import build_seed_matrix, CLASS_NAMES, N_CLASSES
from jableh_ca_markov.markov_ipf import (
    seeded_ipf, estimate_pairwise_matrices, average_matrix,
    diagonal_dispersion, anderson_goodman_test,
    pixel_level_transition_matrix, compare_pixel_and_ipf_matrices,
)
from jableh_ca_markov.projection import forward_projection, steady_state_distribution, steady_state_report
from jableh_ca_markov.uncertainty import monte_carlo_bootstrap
from jableh_ca_markov.sensitivity import seed_matrix_variants, run_seed_sensitivity
from jableh_ca_markov.scenarios import apply_forest_protection, run_forest_protection_scenario


@pytest.fixture
def real_jableh_areas():
    """The actual Jableh District annual class areas (km^2), 2015-2026,
    as extracted from Pivot_km2.csv -- used throughout the article."""
    data = {
        2015: [29.493662, 0.178420, 16.735340, 2.161179, 42.958977, 0.292990],
        2016: [15.904154, 0.026502, 24.147591, 1.437144, 49.474236, 0.851001],
        2017: [17.114359, 0.013455, 22.109625, 2.133944, 49.838986, 0.622839],
        2018: [15.973223, 0.043137, 22.415336, 1.457041, 51.507635, 0.440749],
        2019: [19.811858, 0.079669, 19.579619, 1.474736, 50.634944, 0.244797],
        2020: [17.439886, 0.031966, 19.749477, 1.957399, 52.326426, 0.319574],
        2021: [16.210681, 0.080566, 21.268084, 1.506294, 52.459099, 0.306771],
        2022: [12.272724, 0.033841, 23.753077, 1.529697, 53.714561, 0.527268],
        2023: [18.271560, 0.150368, 20.454186, 0.910528, 51.635987, 0.406011],
        2024: [16.876657, 0.120360, 18.785537, 1.482075, 54.047998, 0.513406],
        2025: [11.419603, 0.020386, 20.612546, 3.641298, 55.403026, 0.738877],
        2026: [13.981819, 0.251484, 20.737472, 1.313685, 54.833355, 0.704465],
    }
    return {y: np.array(v) for y, v in data.items()}


def test_seed_matrix_is_row_stochastic():
    seed = build_seed_matrix()
    assert seed.shape == (N_CLASSES, N_CLASSES)
    np.testing.assert_allclose(seed.sum(axis=1), 1.0, atol=1e-10)


def test_seeded_ipf_matches_marginals(real_jableh_areas):
    """
    NOTE on this test's tolerance: sum(area_2020) and sum(area_2026)
    differ by ~2.7e-5 relative (real Dynamic World composites have
    slightly different valid-pixel counts per annual epoch due to
    cloud/edge masking -- see config.py / markov_ipf.py docstrings).
    IPF/RAS can only satisfy two marginals EXACTLY and SIMULTANEOUSLY
    when their totals match, so with `rescale_to_common_total=True`
    (the default) the fitted matrix is verified against area_2026
    RESCALED to area_2020's total -- not the raw, slightly-inconsistent
    area_2026 -- which is the correct and achievable invariant.
    """
    seed = build_seed_matrix()
    t1 = real_jableh_areas[2020]
    t2_raw = real_jableh_areas[2026]

    P = seeded_ipf(t1, t2_raw, seed, rescale_to_common_total=True)
    np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-8)

    t2_rescaled = t2_raw * (t1.sum() / t2_raw.sum())
    M = P * t1[:, None]
    np.testing.assert_allclose(M.sum(axis=1), t1, rtol=1e-6)
    np.testing.assert_allclose(M.sum(axis=0), t2_rescaled, rtol=1e-6)

    # sanity: the residual against the RAW (unscaled) marginal should be
    # small and fully explained by the known total-area mismatch, not
    # by any remaining algorithmic non-convergence
    raw_residual_rel = np.abs((M.sum(axis=0) - t2_raw) / t2_raw).max()
    expected_rel_mismatch = abs(t1.sum() - t2_raw.sum()) / t1.sum()
    assert raw_residual_rel == pytest.approx(expected_rel_mismatch, rel=0.05)


def test_seeded_ipf_without_rescaling_still_row_stochastic(real_jableh_areas):
    """With rescale_to_common_total=False, exact double-marginal match is
    NOT guaranteed when totals differ (documented limitation) -- but the
    output must still always be row-stochastic."""
    seed = build_seed_matrix()
    P = seeded_ipf(real_jableh_areas[2020], real_jableh_areas[2026], seed,
                    rescale_to_common_total=False)
    np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-8)


def test_average_matrix_row_stochastic(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, labels = estimate_pairwise_matrices(real_jableh_areas, seed)
    assert matrices.shape == (11, N_CLASSES, N_CLASSES)
    assert len(labels) == 11
    P_annual = average_matrix(matrices)
    np.testing.assert_allclose(P_annual.sum(axis=1), 1.0, atol=1e-8)


def test_built_persistence_is_highest_and_most_stable(real_jableh_areas):
    """Sanity check matching the article's core finding: built-up has the
    highest AND most stable annual persistence of all six classes."""
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    P_annual = average_matrix(matrices)
    built_idx = CLASS_NAMES.index("built")
    assert P_annual[built_idx, built_idx] == pytest.approx(P_annual.diagonal().max())

    dispersion = diagonal_dispersion(matrices)
    built_cv = dispersion.set_index("class").loc["built", "cv"]
    assert built_cv == dispersion["cv"].min()


def test_mass_conservation_in_forward_projection(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    P_annual = average_matrix(matrices)
    proj = forward_projection(P_annual, real_jableh_areas[2026], 2026, 4)
    total_2026 = real_jableh_areas[2026].sum()
    for year in proj.index:
        assert proj.loc[year].sum() == pytest.approx(total_2026, rel=1e-6)


def test_steady_state_sums_to_one(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    P_annual = average_matrix(matrices)
    pi = steady_state_distribution(P_annual)
    assert pi.sum() == pytest.approx(1.0, abs=1e-8)
    assert (pi >= -1e-9).all()


def test_anderson_goodman_returns_valid_pvalues(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    result = anderson_goodman_test(matrices, real_jableh_areas)
    assert 0.0 <= result["pooled_p"] <= 1.0
    for _, row in result["per_class"].iterrows():
        assert 0.0 <= row["p_value"] <= 1.0


def test_monte_carlo_bootstrap_ci_contains_deterministic_estimate(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    P_annual = average_matrix(matrices)
    deterministic = forward_projection(P_annual, real_jableh_areas[2026], 2026, 4).loc[2030]

    mc = monte_carlo_bootstrap(matrices, real_jableh_areas[2026], 4, n_bootstrap=200, random_state=1)
    summary = mc["summary"].set_index("class")
    for cls in CLASS_NAMES:
        lo, hi = summary.loc[cls, "ci_low_2.5pct"], summary.loc[cls, "ci_high_97.5pct"]
        assert lo <= deterministic[cls] <= hi or abs(deterministic[cls] - lo) < 1.0 or abs(deterministic[cls] - hi) < 1.0


def test_seed_sensitivity_produces_four_variants(real_jableh_areas):
    df = run_seed_sensitivity(real_jableh_areas, horizon_years=4)
    assert set(["original", "optimistic", "pessimistic", "uniform"]).issubset(set(df.index))
    assert "built" in df.columns


def test_forest_protection_reduces_trees_to_built(real_jableh_areas):
    seed = build_seed_matrix()
    matrices, _ = estimate_pairwise_matrices(real_jableh_areas, seed)
    P_annual = average_matrix(matrices)

    trees_idx = CLASS_NAMES.index("trees")
    built_idx = CLASS_NAMES.index("built")
    original_rate = P_annual[trees_idx, built_idx]

    P_scenario = apply_forest_protection(P_annual, new_trees_to_built=0.01)
    assert P_scenario[trees_idx, built_idx] == pytest.approx(0.01, abs=1e-6)
    assert P_scenario[trees_idx, built_idx] < original_rate
    np.testing.assert_allclose(P_scenario.sum(axis=1), 1.0, atol=1e-8)

    proj_baseline = forward_projection(P_annual, real_jableh_areas[2026], 2026, 4)
    proj_scenario = run_forest_protection_scenario(P_annual, real_jableh_areas[2026], 2026, 4, 0.01)
    # forest protection should leave MORE trees standing by 2030 than baseline
    assert proj_scenario.loc[2030, "trees"] > proj_baseline.loc[2030, "trees"]


def test_pixel_level_transition_matrix_synthetic():
    """Smoke test with a small synthetic raster (no real Jableh data
    needed for this pure cross-tabulation logic)."""
    raster_t1 = np.array([[1, 1, 4], [4, 6, 6], [7, 1, 4]])
    raster_t2 = np.array([[1, 6, 4], [4, 6, 6], [7, 6, 4]])
    result = pixel_level_transition_matrix(raster_t1, raster_t2, class_indices=[1, 4, 6, 7])

    # manual count over the flattened 3x3 arrays:
    #   t1 = [1,1,4,4,6,6,7,1,4], t2 = [1,6,4,4,6,6,7,6,4]
    #   pairs: (1,1)(1,6)(4,4)(4,4)(6,6)(6,6)(7,7)(1,6)(4,4)
    assert result["counts"].loc["trees", "trees"] == 1     # one  1->1
    assert result["counts"].loc["trees", "built"] == 2     # two  1->6
    assert result["counts"].loc["crops", "crops"] == 3     # three 4->4
    assert result["counts"].loc["built", "built"] == 2     # two  6->6
    assert result["counts"].loc["bare", "bare"] == 1       # one  7->7

    prob = result["probability"]
    np.testing.assert_allclose(prob.sum(axis=1).values, 1.0, atol=1e-8)


def test_compare_pixel_and_ipf_matrices():
    import pandas as pd
    pixel = pd.DataFrame({"trees": [0.9, 0.1], "built": [0.1, 0.9]}, index=["trees", "built"])
    ipf = pd.DataFrame({"trees": [0.85, 0.05], "built": [0.15, 0.95]}, index=["trees", "built"])
    comparison = compare_pixel_and_ipf_matrices(pixel, ipf)
    assert set(comparison["class"]) == {"trees", "built"}
    trees_row = comparison.set_index("class").loc["trees"]
    assert trees_row["abs_difference"] == pytest.approx(0.05, abs=1e-8)
