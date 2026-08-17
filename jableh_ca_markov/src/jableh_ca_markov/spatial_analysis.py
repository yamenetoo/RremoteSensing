"""
spatial_analysis.py
====================
Pixel-level cross-tabulated transition maps, directional decomposition
(compass sectors, centroid migration, Standard Deviational Ellipse),
and Gaussian KDE hotspot detection of built-up gain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from scipy import ndimage
except ImportError:  # pragma: no cover
    ndimage = None


# ----------------------------------------------------------------------
# Pixel-level transition maps for a specific class pair
# ----------------------------------------------------------------------
def class_transition_mask(raster_t1: np.ndarray, raster_t2: np.ndarray,
                            code_t1: int, code_t2: int) -> np.ndarray:
    """Binary mask of pixels that transitioned from `code_t1` at t1 to
    `code_t2` at t2."""
    return ((raster_t1 == code_t1) & (raster_t2 == code_t2)).astype(np.uint8)


# ----------------------------------------------------------------------
# Sector-based directional growth decomposition
# ----------------------------------------------------------------------
SECTOR_NAMES = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]


def sector_growth_series(built_masks_by_year: dict[int, np.ndarray],
                          pixel_area_km2: float,
                          center_year: int | None = None) -> pd.DataFrame:
    """
    Decompose built-up area into 8 compass sectors centred on the
    built-up centroid of `center_year` (defaults to the first year in
    the series), and return the annual area (km^2) per sector.
    """
    years = sorted(built_masks_by_year)
    center_year = center_year or years[0]

    rows0, cols0 = np.where(built_masks_by_year[center_year])
    center_y, center_x = rows0.mean(), cols0.mean()

    shape = built_masks_by_year[center_year].shape
    y_idx, x_idx = np.indices(shape)
    pixel_angles = np.arctan2(y_idx - center_y, x_idx - center_x)

    n_sectors = len(SECTOR_NAMES)
    angles = np.linspace(-np.pi, np.pi, n_sectors + 1)[:-1] + np.pi / n_sectors

    series = {name: [] for name in SECTOR_NAMES}
    for y in years:
        mask = built_masks_by_year[y]
        for i, name in enumerate(SECTOR_NAMES):
            ang_min = angles[i] - np.pi / n_sectors
            ang_max = angles[i] + np.pi / n_sectors
            if ang_min < -np.pi:
                cond = (pixel_angles >= ang_min + 2 * np.pi) | (pixel_angles < ang_max)
            elif ang_max > np.pi:
                cond = (pixel_angles >= ang_min) | (pixel_angles < ang_max - 2 * np.pi)
            else:
                cond = (pixel_angles >= ang_min) & (pixel_angles < ang_max)
            series[name].append(np.count_nonzero(mask & cond) * pixel_area_km2)

    return pd.DataFrame(series, index=years)


def sector_growth_rates(sector_df: pd.DataFrame) -> pd.Series:
    """OLS linear slope (km^2/yr) per sector."""
    years = np.array(sector_df.index, dtype=float)
    slopes = {}
    for col in sector_df.columns:
        slope = np.polyfit(years, sector_df[col].values, 1)[0]
        slopes[col] = slope
    return pd.Series(slopes, name="growth_rate_km2_per_year")


# ----------------------------------------------------------------------
# Centroid migration
# ----------------------------------------------------------------------
def centroid_series(built_masks_by_year: dict[int, np.ndarray]) -> pd.DataFrame:
    rows = []
    for y in sorted(built_masks_by_year):
        r, c = np.where(built_masks_by_year[y])
        rows.append({"year": y, "x": c.mean(), "y": r.mean()})
    return pd.DataFrame(rows).set_index("year")


def centroid_shift_metres(centroid_df: pd.DataFrame, pixel_size_x_m: float,
                            pixel_size_y_m: float) -> dict:
    first, last = centroid_df.iloc[0], centroid_df.iloc[-1]
    dx_px = last["x"] - first["x"]
    dy_px = last["y"] - first["y"]
    return {
        "dx_px": dx_px, "dy_px": dy_px,
        "dx_m": dx_px * pixel_size_x_m,
        "dy_m": dy_px * pixel_size_y_m,
    }


# ----------------------------------------------------------------------
# Standard Deviational Ellipse (SDE)
# ----------------------------------------------------------------------
def standard_deviational_ellipse(mask: np.ndarray) -> dict | None:
    """Fit a Standard Deviational Ellipse to a binary pixel mask.
    Returns center, semi-axis lengths (px), and orientation angle (deg)."""
    r, c = np.where(mask)
    if len(r) < 3:
        return None
    center = (c.mean(), r.mean())
    cov = np.cov(np.column_stack((c, r)), rowvar=False)
    evals, evecs = np.linalg.eigh(cov)
    order = evals.argsort()[::-1]
    evals, evecs = evals[order], evecs[:, order]
    angle = float(np.degrees(np.arctan2(evecs[1, 0], evecs[0, 0])))
    return {
        "center": center,
        "semi_major_px": float(np.sqrt(evals[0])),
        "semi_minor_px": float(np.sqrt(evals[1])),
        "angle_deg": angle,
    }


# ----------------------------------------------------------------------
# Gaussian KDE hotspot detection
# ----------------------------------------------------------------------
def hotspot_analysis(gain_mask: np.ndarray, sigma_px: float = 30,
                       percentile: float = 95) -> dict:
    """
    Gaussian-kernel density hotspot detection on a binary gain map.
    Returns the normalised density surface and a binary hotspot mask
    (top `percentile`% of non-zero density values).
    """
    density = ndimage.gaussian_filter(gain_mask.astype(np.float32), sigma=sigma_px,
                                        mode="constant", cval=0)
    density_max = density.max()
    density_norm = density / density_max if density_max > 0 else density

    nonzero = density_norm[density_norm > 0]
    threshold = float(np.percentile(nonzero, percentile)) if nonzero.size else 0.0
    hotspots = (density_norm >= threshold).astype(np.uint8)

    return {
        "density_norm": density_norm,
        "hotspots": hotspots,
        "threshold": threshold,
        "gain_pixels": int(gain_mask.sum()),
        "hotspot_pixels": int(hotspots.sum()),
    }
