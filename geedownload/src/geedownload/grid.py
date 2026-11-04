"""Pixel-grid helpers: choose a UTM zone, snap bounds to the pixel grid and split into tiles.

Tiles share one global pixel grid (via `crs_transform`), so they mosaic with no sub-pixel shift.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from pyproj import CRS, Transformer

Bounds = Tuple[float, float, float, float]   # x0, y0, x1, y1 in the target CRS


def utm_crs_for(lon: float, lat: float) -> str:
    zone = min(max(int((lon + 180) // 6) + 1, 1), 60)
    return f"EPSG:{(326 if lat >= 0 else 327) * 100 + zone}"


def step_in_crs_units(scale_m: float, crs: str) -> float:
    """Pixel size in the CRS's own units (metres, or degrees for geographic CRS)."""
    return scale_m / 111320.0 if CRS.from_user_input(crs).is_geographic else float(scale_m)


def project_bbox(bbox: Sequence[float], crs: str, densify: int = 20) -> Bounds:
    """Project a lon/lat bbox (w, s, e, n) into `crs`, following the curved edges."""
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    w, s, e, n = bbox
    xs, ys = [], []
    for i in range(densify + 1):
        f = i / densify
        for lon, lat in ((w + (e - w) * f, s), (w + (e - w) * f, n), (w, s + (n - s) * f), (e, s + (n - s) * f)):
            x, y = t.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def snap_bounds(b: Bounds, step: float) -> Bounds:
    x0, y0, x1, y1 = b
    return (math.floor(x0 / step) * step, math.floor(y0 / step) * step,
            math.ceil(x1 / step) * step, math.ceil(y1 / step) * step)


def grid_shape(b: Bounds, step: float) -> Tuple[int, int]:
    """(rows, cols) of the grid covering `b`."""
    return max(1, round((b[3] - b[1]) / step)), max(1, round((b[2] - b[0]) / step))


def make_tiles(b: Bounds, step: float, max_side_px: int = 1500) -> List[Bounds]:
    """Split bounds into tiles of at most max_side_px x max_side_px pixels (row-major from top-left)."""
    x0, y0, x1, y1 = b
    rows, cols = grid_shape(b, step)
    tiles: List[Bounds] = []
    for r0 in range(0, rows, max_side_px):
        r1 = min(r0 + max_side_px, rows)
        for c0 in range(0, cols, max_side_px):
            c1 = min(c0 + max_side_px, cols)
            tiles.append((x0 + c0 * step, y1 - r1 * step, x0 + c1 * step, y1 - r0 * step))
    return tiles


def crs_transform(b: Bounds, step: float) -> List[float]:
    """Affine [scaleX, 0, originX, 0, -scaleY, originY] with the origin at the top-left of `b`."""
    return [step, 0, b[0], 0, -step, b[3]]
