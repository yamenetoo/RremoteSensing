"""
scenarios.py
=============
Policy "what-if" scenario simulation (revision item 4.3):

  Scenario 1 (Green Belt)       : no-build buffer zone along the
                                    southern/south-western fringe
                                    (pixel-level; requires real rasters).
  Scenario 2 (Forest Protection): reduce the trees -> built transition
                                    probability in P_annual (area-level;
                                    fully computable here).
  Scenario 3 (Combined)         : both measures together.

The forest-protection scenario is a pure modification of the transition
matrix, so it can be run end-to-end with only the area time series
(already available). The green-belt scenario requires masking real
pixels by geographic buffer and therefore needs the raster pipeline;
its function is provided ready-to-run against real data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CLASS_NAMES
from .projection import forward_projection


# ----------------------------------------------------------------------
# Scenario 2: Forest Protection (area-level, fully computable)
# ----------------------------------------------------------------------
def apply_forest_protection(P_annual: np.ndarray, new_trees_to_built: float) -> np.ndarray:
    """
    Return a modified copy of P_annual with the trees->built transition
    probability reduced to `new_trees_to_built`, redistributing the
    removed probability mass proportionally across trees' other
    off-diagonal entries (preserving row-stochasticity).
    """
    P = P_annual.copy()
    trees_idx = CLASS_NAMES.index("trees")
    built_idx = CLASS_NAMES.index("built")

    old_val = P[trees_idx, built_idx]
    delta = old_val - new_trees_to_built
    if delta <= 0:
        P[trees_idx, built_idx] = new_trees_to_built
        return P / P.sum(axis=1, keepdims=True)

    other_mask = np.ones(len(CLASS_NAMES), dtype=bool)
    other_mask[built_idx] = False
    other_mask[trees_idx] = False  # do not touch self-persistence directly here
    other_sum = P[trees_idx, other_mask].sum()

    P[trees_idx, built_idx] = new_trees_to_built
    if other_sum > 0:
        P[trees_idx, other_mask] += delta * (P[trees_idx, other_mask] / other_sum)
    else:
        P[trees_idx, trees_idx] += delta

    return P / P.sum(axis=1, keepdims=True)


def run_forest_protection_scenario(
    P_annual: np.ndarray,
    current_state: np.ndarray,
    current_year: int,
    horizon_years: int,
    new_trees_to_built: float = 0.01,
) -> pd.DataFrame:
    """Project forward under the forest-protection transition matrix."""
    P_scenario = apply_forest_protection(P_annual, new_trees_to_built)
    return forward_projection(P_scenario, current_state, current_year, horizon_years)


# ----------------------------------------------------------------------
# Scenario 1: Green Belt (pixel-level, requires real rasters)
# ----------------------------------------------------------------------
def apply_green_belt_mask(suitability: np.ndarray, buffer_mask: np.ndarray) -> np.ndarray:
    """
    Zero out suitability within a designated no-build buffer (e.g. a
    500 m strip along the southern/south-western district edge).

    `buffer_mask` should be a boolean array (same shape as
    `suitability`) marking the protected zone -- typically produced by
    buffering the district boundary's southern edge with
    geopandas/shapely and rasterising onto the working grid.
    """
    out = suitability.copy()
    out[buffer_mask] = 0.0
    return out


def build_southern_buffer_mask(district_shape, buffer_m: float, transform, crs,
                                 target_shape) -> np.ndarray:
    """
    Construct a rasterised no-build buffer mask along the southern edge
    of the district boundary. Requires geopandas/shapely + rasterio.
    """
    import geopandas as gpd
    from shapely.geometry import box
    from rasterio.features import rasterize

    minx, miny, maxx, maxy = district_shape.bounds
    south_third = box(minx, miny, maxx, miny + (maxy - miny) * 0.35)
    southern_zone = district_shape.intersection(south_third)
    buffered = southern_zone.buffer(buffer_m)

    mask = rasterize(
        [(buffered, 1)], out_shape=target_shape, transform=transform,
        fill=0, dtype=np.uint8,
    )
    return mask.astype(bool)


# ----------------------------------------------------------------------
# Scenario 3: Combined (both measures)
# ----------------------------------------------------------------------
def run_combined_scenario(
    P_annual: np.ndarray,
    current_state: np.ndarray,
    current_year: int,
    horizon_years: int,
    new_trees_to_built: float = 0.01,
    ca_allocation_fn=None,
    ca_allocation_kwargs: dict | None = None,
    green_belt_mask=None,
) -> dict:
    """
    Area-level projection under forest protection (always computed),
    PLUS an optional pixel-level CA run with the green-belt suitability
    mask applied (only if `ca_allocation_fn` and `green_belt_mask` are
    supplied with real raster data).
    """
    area_projection = run_forest_protection_scenario(
        P_annual, current_state, current_year, horizon_years, new_trees_to_built,
    )

    pixel_result = None
    if ca_allocation_fn is not None and green_belt_mask is not None:
        kwargs = dict(ca_allocation_kwargs or {})
        original_fn = kwargs.pop("suitability_hook", None)
        pixel_result = ca_allocation_fn(
            green_belt_mask=green_belt_mask, **kwargs,
        )

    return {"area_projection": area_projection, "pixel_result": pixel_result}


# ----------------------------------------------------------------------
# Comparison table across all scenarios (area-level; Table in Section 3.12)
# ----------------------------------------------------------------------
def compare_scenarios(
    baseline_projection: pd.DataFrame,
    green_belt_projection: pd.DataFrame | None,
    forest_protection_projection: pd.DataFrame,
    combined_projection: pd.DataFrame,
    target_year: int,
) -> pd.DataFrame:
    """Assemble the final scenario-comparison table (built / trees / crops
    at the target year, plus the change from baseline)."""
    rows = []
    scenarios = {
        "Baseline": baseline_projection,
        "Green Belt": green_belt_projection,
        "Forest Protection": forest_protection_projection,
        "Combined": combined_projection,
    }
    baseline_built = baseline_projection.loc[target_year, "built"]
    baseline_trees = baseline_projection.loc[target_year, "trees"]

    for name, proj in scenarios.items():
        if proj is None:
            rows.append({"scenario": name, "built_km2": np.nan, "trees_km2": np.nan,
                         "crops_km2": np.nan, "delta_built": np.nan, "delta_trees": np.nan,
                         "note": "requires real raster pipeline"})
            continue
        built = proj.loc[target_year, "built"]
        trees = proj.loc[target_year, "trees"]
        crops = proj.loc[target_year, "crops"]
        rows.append({
            "scenario": name, "built_km2": built, "trees_km2": trees, "crops_km2": crops,
            "delta_built": built - baseline_built, "delta_trees": trees - baseline_trees,
        })
    return pd.DataFrame(rows).set_index("scenario")
