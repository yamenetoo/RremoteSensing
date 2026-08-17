"""
ca_allocation.py
=================
Spatially explicit Cellular Automata (CA) allocation model. Converts
the Markov quantity projections into pixel-level maps.

Extends the original three-factor suitability surface (distance decay,
land-cover conversion preference, local built density) with two new
factors requested in the revision:

    S(x,y) = S_dist * S_land * (1 + 2*density) * S_slope * S_road

  S_slope = exp(-slope_degrees / 10)   -- flat land favoured
  S_road  = exp(-dist_to_road_m / 1000) -- proximity to roads favoured

Everything in this module operates on real raster arrays (numpy) and
therefore requires `rasterio`/`scipy.ndimage` plus the actual Jableh
GeoTIFF stack -- it is written to run unmodified in the same Colab
environment used earlier in the project, but cannot be executed inside
this packaging/testing environment (no GEE credentials or raw rasters
available here). Every function is unit-testable in isolation with
synthetic arrays, see tests/test_ca_allocation.py.
"""

from __future__ import annotations

import numpy as np

try:
    from scipy import ndimage
except ImportError:  # pragma: no cover - scipy is a hard dependency in practice
    ndimage = None

from .config import CLASS_INDICES, BUILT


# ----------------------------------------------------------------------
# Individual suitability factors
# ----------------------------------------------------------------------
def distance_decay_suitability(built_mask: np.ndarray, pixel_size_m: float, D0: float = 500.0) -> np.ndarray:
    """S_dist = exp(-d / D0), d = Euclidean distance (m) to nearest built pixel."""
    dist_m = ndimage.distance_transform_edt(1 - built_mask) * pixel_size_m
    return np.exp(-dist_m / D0)


def land_cover_preference_suitability(lulc: np.ndarray, conv_to_built: np.ndarray,
                                        class_indices: list[int] | None = None) -> np.ndarray:
    """S_land: per-pixel suitability from the class's estimated
    Markov probability of transitioning to built (P_annual[:, built])."""
    class_indices = class_indices or CLASS_INDICES
    s_land = np.zeros_like(lulc, dtype=np.float32)
    for i, code in enumerate(class_indices):
        if code == BUILT:
            continue
        s_land[lulc == code] = conv_to_built[i]
    max_val = s_land.max() if s_land.max() > 0 else 1.0
    return s_land / max_val


def local_density_suitability(built_mask: np.ndarray, window: int = 5) -> np.ndarray:
    """S_density multiplier = 1 + 2*(fraction of built pixels in a
    window x window neighbourhood) -- agglomeration effect."""
    kernel = np.ones((window, window)) / (window * window)
    density = ndimage.convolve(built_mask.astype(np.float32), kernel, mode="constant", cval=0)
    return 1.0 + 2.0 * density


def slope_suitability(slope_degrees: np.ndarray, decay: float = 10.0) -> np.ndarray:
    """NEW (revision 2.3): S_slope = exp(-slope / decay). Flat land (slope
    -> 0) has suitability -> 1; steep land is strongly discouraged."""
    return np.exp(-np.clip(slope_degrees, 0, None) / decay)


def road_distance_suitability(dist_to_road_m: np.ndarray, decay: float = 1000.0) -> np.ndarray:
    """NEW (revision 2.3): S_road = exp(-distance_to_road / decay).
    Pixels on/near a major road have suitability -> 1."""
    return np.exp(-np.clip(dist_to_road_m, 0, None) / decay)


def load_and_normalise_slope(dem_path: str, target_shape, target_transform, target_crs) -> np.ndarray:
    """
    Load an SRTM (or any) DEM, compute slope in degrees, and resample to
    match the working Dynamic World grid. Requires `rasterio` and
    `richdem` (or `xarray`/`rioxarray` equivalents) -- richdem is used
    here for a simple, dependency-light slope computation.
    """
    import rasterio
    from rasterio.warp import reproject, Resampling
    import richdem as rd

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        dem_transform = src.transform
        dem_crs = src.crs

    rd_dem = rd.rdarray(dem, no_data=-9999)
    slope = rd.TerrainAttribute(rd_dem, attrib="slope_degrees")
    slope = np.asarray(slope)

    resampled = np.zeros(target_shape, dtype=np.float32)
    reproject(
        source=slope, destination=resampled,
        src_transform=dem_transform, src_crs=dem_crs,
        dst_transform=target_transform, dst_crs=target_crs,
        resampling=Resampling.bilinear,
    )
    return resampled


def load_and_normalise_road_distance(roads_path: str, target_shape, target_transform, target_crs,
                                       pixel_size_m: float) -> np.ndarray:
    """
    Load a road network (e.g. OSM primary/secondary roads, GeoPackage or
    Shapefile), rasterise it onto the working grid, and compute the
    Euclidean distance (m) to the nearest road pixel.
    """
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize

    roads = gpd.read_file(roads_path).to_crs(target_crs)
    road_mask = rasterize(
        [(geom, 1) for geom in roads.geometry],
        out_shape=target_shape,
        transform=target_transform,
        fill=0,
        dtype=np.uint8,
    )
    return ndimage.distance_transform_edt(1 - road_mask) * pixel_size_m


# ----------------------------------------------------------------------
# Combined suitability surface (Eq. 4, extended)
# ----------------------------------------------------------------------
def compute_suitability(
    built_mask: np.ndarray,
    lulc: np.ndarray,
    conv_to_built: np.ndarray,
    pixel_size_m: float,
    D0: float = 500.0,
    window: int = 5,
    slope_degrees: np.ndarray | None = None,
    road_distance_m: np.ndarray | None = None,
    class_indices: list[int] | None = None,
) -> np.ndarray:
    """
    Combined CA suitability surface. If `slope_degrees` and/or
    `road_distance_m` are omitted, those factors default to 1.0
    everywhere (i.e. the original three-factor model is recovered
    exactly), so this function is backward-compatible with the
    pre-revision pipeline.
    """
    s_dist = distance_decay_suitability(built_mask, pixel_size_m, D0)
    s_land = land_cover_preference_suitability(lulc, conv_to_built, class_indices)
    s_dens = local_density_suitability(built_mask, window)

    s_slope = slope_suitability(slope_degrees) if slope_degrees is not None else 1.0
    s_road = road_distance_suitability(road_distance_m) if road_distance_m is not None else 1.0

    s_total = s_dist * s_land * s_dens * s_slope * s_road
    s_total = np.where(built_mask == 1, 0.0, s_total)
    return s_total


# ----------------------------------------------------------------------
# Annual allocation loop
# ----------------------------------------------------------------------
def run_ca_allocation(
    lulc_base: np.ndarray,
    built_targets_by_year: dict[int, float],
    pixel_area_km2: float,
    pixel_size_m: float,
    conv_to_built: np.ndarray,
    D0: float = 500.0,
    window: int = 5,
    slope_degrees: np.ndarray | None = None,
    road_distance_m: np.ndarray | None = None,
    class_indices: list[int] | None = None,
    recompute_every_step: bool = True,
) -> dict:
    """
    Iteratively allocate new built-up pixels year by year to match the
    Markov-projected target area, using the combined suitability surface.

    Parameters
    ----------
    built_targets_by_year : dict[int, float]
        {year: target_built_area_km2}, sorted ascending by year, e.g.
        {2027: 55.53, 2028: 56.22, 2029: 56.85, 2030: 57.43}.

    Returns
    -------
    dict with 'final_lulc' (np.ndarray) and 'allocation_log' (list of
    dicts recording pixels needed/added per year).
    """
    class_indices = class_indices or CLASS_INDICES
    built_mask = (lulc_base == BUILT).astype(np.uint8)
    lulc_current = lulc_base.copy()
    log = []

    suitability = compute_suitability(
        built_mask, lulc_current, conv_to_built, pixel_size_m,
        D0=D0, window=window, slope_degrees=slope_degrees,
        road_distance_m=road_distance_m, class_indices=class_indices,
    )

    for year in sorted(built_targets_by_year):
        target_px = int(round(built_targets_by_year[year] / pixel_area_km2))
        current_px = int(built_mask.sum())
        needed = max(0, target_px - current_px)
        log.append({"year": year, "current_px": current_px, "target_px": target_px, "needed_px": needed})

        if needed > 0:
            non_built = built_mask == 0
            candidate_suit = suitability[non_built]
            needed_capped = min(needed, candidate_suit.size)
            flat_idx = np.argpartition(candidate_suit, -needed_capped)[-needed_capped:]
            rows, cols = np.where(non_built)
            built_mask[rows[flat_idx], cols[flat_idx]] = 1

        if recompute_every_step:
            suitability = compute_suitability(
                built_mask, lulc_current, conv_to_built, pixel_size_m,
                D0=D0, window=window, slope_degrees=slope_degrees,
                road_distance_m=road_distance_m, class_indices=class_indices,
            )

    lulc_final = lulc_current.copy()
    lulc_final[built_mask == 1] = BUILT
    return {"final_lulc": lulc_final, "allocation_log": log}
