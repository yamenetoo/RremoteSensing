"""NaN-aware spectral preprocessing on 2-D arrays of shape (n_spectra, n_bands).

All functions accept ``X`` with NaN marking missing/deleted channels and return
new arrays; inputs are never modified. Wavelengths are in nanometres.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np
from scipy.signal import savgol_filter

from .sensors import Sensor, get_sensor

_FWHM_TO_SIGMA = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))


def _as2d(X) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    return X[None, :] if X.ndim == 1 else X


# ---------------------------------------------------------------- resampling
def resample(
    wl_src, X, wl_dst, fwhm: Optional[float] = None, gap_factor: Optional[float] = 3.0
) -> np.ndarray:
    """Resample spectra to a new wavelength grid.

    Linear interpolation over valid channels only, no extrapolation (NaN outside
    the source range). Deleted/bad channels stay missing: target points whose two
    neighbouring valid source channels are more than ``gap_factor`` source steps
    apart are NaN instead of being bridged (set ``gap_factor=None`` to bridge gaps).
    If ``fwhm`` is given, a Gaussian window of that width is used instead
    (appropriate when the target grid is much coarser than the source).
    """
    wl_src = np.asarray(wl_src, float)
    wl_dst = np.asarray(wl_dst, float)
    X = _as2d(X)
    if fwhm is not None:
        return convolve_to_bands(wl_src, X, wl_dst, np.full(len(wl_dst), float(fwhm)))
    out = np.full((X.shape[0], len(wl_dst)), np.nan)
    max_gap = gap_factor * float(np.median(np.diff(wl_src))) if gap_factor and len(wl_src) > 1 else None
    for i, y in enumerate(X):
        ok = np.isfinite(y)
        if ok.sum() < 2:
            continue
        x, v = wl_src[ok], y[ok]
        inside = (wl_dst >= x[0]) & (wl_dst <= x[-1])
        if max_gap is not None:
            idx = np.searchsorted(x, wl_dst)
            right = np.clip(idx, 1, len(x) - 1)
            exact = x[np.clip(idx, 0, len(x) - 1)] == wl_dst
            inside &= ((x[right] - x[right - 1]) <= max_gap) | exact
        out[i, inside] = np.interp(wl_dst[inside], x, v)
    return out


def _weights(wl, center, fwhm, shape):
    if shape == "box":
        return ((wl >= center - fwhm / 2) & (wl <= center + fwhm / 2)).astype(float)
    sigma = fwhm * _FWHM_TO_SIGMA
    w = np.exp(-0.5 * ((wl - center) / sigma) ** 2)
    w[np.abs(wl - center) > 3 * sigma] = 0.0
    return w


def convolve_to_bands(
    wl, X, centers, fwhms, shapes: Optional[Sequence[str]] = None, min_coverage: float = 0.8
) -> np.ndarray:
    """Weighted average of each spectrum over each target band (Gaussian or box SRF).

    A band is NaN when less than ``min_coverage`` of its weight lies on valid channels.
    The source grid should be at least ~3x finer than the narrowest band.
    """
    wl = np.asarray(wl, float)
    X = _as2d(X)
    centers = np.asarray(centers, float)
    fwhms = np.asarray(fwhms, float)
    shapes = shapes or ["gaussian"] * len(centers)
    out = np.full((X.shape[0], len(centers)), np.nan)
    valid = np.isfinite(X)
    Xz = np.where(valid, X, 0.0)
    for j, (c, f, s) in enumerate(zip(centers, fwhms, shapes)):
        w = _weights(wl, c, f, s)
        total = w.sum()
        if total <= 0:
            continue
        num = Xz @ w
        den = valid @ w
        with np.errstate(invalid="ignore", divide="ignore"):
            res = num / den
        res[den / total < min_coverage] = np.nan
        out[:, j] = res
    return out


def to_sensor(wl, X, sensor) -> Tuple[np.ndarray, Sensor]:
    """Convolve spectra to a sensor's bands (see :mod:`usgs_splib07.sensors`)."""
    s = get_sensor(sensor)
    step = float(np.median(np.diff(np.asarray(wl, float))))
    narrow = min(b.fwhm for b in s.bands)
    if step > narrow / 3:
        import warnings
        warnings.warn(
            f"Source step ({step:.1f} nm) is coarse for the narrowest {s.name} band ({narrow:.0f} nm); "
            "build the library with a finer step (1-5 nm) for accurate band values.",
            stacklevel=2,
        )
    out = convolve_to_bands(wl, X, s.centers, s.fwhms, [b.shape for b in s.bands])
    return out, s


def convolve_srf(wl, X, srf_wl, srf_resp, min_coverage: float = 0.8) -> np.ndarray:
    """Convolve to ONE band using an arbitrary spectral response function (e.g. the official ESA file)."""
    wl = np.asarray(wl, float)
    w = np.interp(wl, np.asarray(srf_wl, float), np.asarray(srf_resp, float), left=0.0, right=0.0)
    X = _as2d(X)
    valid = np.isfinite(X)
    num = np.where(valid, X, 0.0) @ w
    den = valid @ w
    with np.errstate(invalid="ignore", divide="ignore"):
        res = num / den
    res[den / w.sum() < min_coverage] = np.nan
    return res


# ---------------------------------------------------------------- smoothing & derivatives
def _fill_gaps(wl, X):
    X = _as2d(X).copy()
    for i in range(X.shape[0]):
        ok = np.isfinite(X[i])
        if ok.sum() >= 2 and not ok.all():
            lo, hi = np.where(ok)[0][[0, -1]]
            seg = slice(lo, hi + 1)
            X[i, seg] = np.interp(wl[seg], wl[ok], X[i, ok])
    return X


def _savgol(wl, X, window, poly, deriv):
    wl = np.asarray(wl, float)
    delta = float(np.median(np.diff(wl)))
    Xf = _fill_gaps(wl, X)
    out = np.full_like(Xf, np.nan)
    for i, y in enumerate(Xf):
        ok = np.isfinite(y)
        if ok.sum() < window:
            continue
        lo, hi = np.where(ok)[0][[0, -1]]
        out[i, lo:hi + 1] = savgol_filter(y[lo:hi + 1], window, poly, deriv=deriv, delta=delta)
    out[~np.isfinite(_as2d(X))] = np.nan  # keep original gaps as gaps
    return out


def smooth(wl, X, window: int = 11, poly: int = 3) -> np.ndarray:
    """Savitzky-Golay smoothing (window in channels, must be odd)."""
    return _savgol(wl, X, window, poly, 0)


def derivative(wl, X, order: int = 1, window: int = 11, poly: int = 3) -> np.ndarray:
    """Savitzky-Golay derivative with respect to wavelength (units: reflectance per nm^order)."""
    return _savgol(wl, X, window, max(poly, order), order)


# ---------------------------------------------------------------- continuum removal
def _upper_hull(x, y):
    idx = []
    for i in range(len(x)):
        while len(idx) >= 2:
            a, b = idx[-2], idx[-1]
            cross = (x[b] - x[a]) * (y[i] - y[a]) - (y[b] - y[a]) * (x[i] - x[a])
            if cross >= 0:  # b lies on or below segment a-i
                idx.pop()
            else:
                break
        idx.append(i)
    return idx


def continuum_removal(wl, X) -> np.ndarray:
    """Divide each spectrum by its upper convex hull (values in [0, 1], absorption = dips)."""
    wl = np.asarray(wl, float)
    X = _as2d(X)
    out = np.full_like(X, np.nan)
    for i, y in enumerate(X):
        ok = np.where(np.isfinite(y))[0]
        if len(ok) < 3:
            continue
        x, v = wl[ok], y[ok]
        h = _upper_hull(x, v)
        cont = np.interp(x, x[h], v[h])
        with np.errstate(invalid="ignore", divide="ignore"):
            out[i, ok] = v / cont
    return out


# ---------------------------------------------------------------- normalisation
def snv(X) -> np.ndarray:
    """Standard normal variate per spectrum."""
    X = _as2d(X)
    mu = np.nanmean(X, axis=1, keepdims=True)
    sd = np.nanstd(X, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (X - mu) / sd


def normalize(X, method: str = "l2") -> np.ndarray:
    """Per-spectrum scaling: ``l2``, ``max``, ``minmax`` or ``area`` (sum)."""
    X = _as2d(X)
    with np.errstate(invalid="ignore", divide="ignore"):
        if method == "l2":
            return X / np.sqrt(np.nansum(X ** 2, axis=1, keepdims=True))
        if method == "max":
            return X / np.nanmax(X, axis=1, keepdims=True)
        if method == "minmax":
            lo = np.nanmin(X, axis=1, keepdims=True)
            hi = np.nanmax(X, axis=1, keepdims=True)
            return (X - lo) / (hi - lo)
        if method == "area":
            return X / np.nansum(X, axis=1, keepdims=True)
    raise ValueError(f"Unknown normalisation '{method}'")


# ---------------------------------------------------------------- indices & features
def _nearest(wl, target):
    wl = np.asarray(wl, float)
    return int(np.argmin(np.abs(wl - target)))


def normalized_difference(wl, X, a_nm: float, b_nm: float) -> np.ndarray:
    """(A - B) / (A + B) using the channels nearest to the two wavelengths (e.g. NDVI: 842, 665)."""
    X = _as2d(X)
    a, b = X[:, _nearest(wl, a_nm)], X[:, _nearest(wl, b_nm)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (a - b) / (a + b)


def band_ratio(wl, X, a_nm: float, b_nm: float) -> np.ndarray:
    X = _as2d(X)
    with np.errstate(invalid="ignore", divide="ignore"):
        return X[:, _nearest(wl, a_nm)] / X[:, _nearest(wl, b_nm)]


def band_depth(wl, X, left_nm: float, center_nm: float, right_nm: float) -> np.ndarray:
    """Absorption depth at ``center_nm`` relative to a straight continuum between two shoulders."""
    wl = np.asarray(wl, float)
    X = _as2d(X)
    il, ic, ir = (_nearest(wl, v) for v in (left_nm, center_nm, right_nm))
    t = (wl[ic] - wl[il]) / (wl[ir] - wl[il])
    cont = X[:, il] + t * (X[:, ir] - X[:, il])
    with np.errstate(invalid="ignore", divide="ignore"):
        return 1.0 - X[:, ic] / cont


# ---------------------------------------------------------------- matching
def spectral_angle(X, ref, min_overlap: int = 3) -> np.ndarray:
    """Spectral angle (radians) between every row of ``X`` and ``ref``, using shared valid channels."""
    X = _as2d(X)
    ref = np.asarray(ref, float).ravel()
    m = np.isfinite(X) & np.isfinite(ref)[None, :]
    Xz = np.where(m, X, 0.0)
    rz = np.where(m, ref[None, :], 0.0)
    dot = (Xz * rz).sum(1)
    nx = np.sqrt((Xz ** 2).sum(1))
    nr = np.sqrt((rz ** 2).sum(1))
    with np.errstate(invalid="ignore", divide="ignore"):
        ang = np.arccos(np.clip(dot / (nx * nr), -1.0, 1.0))
    ang[m.sum(1) < min_overlap] = np.nan
    return ang
