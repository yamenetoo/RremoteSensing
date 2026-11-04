"""Satellite and airborne images: read them, mask them, and match every pixel to the library.

Works with any sensor, multispectral (Sentinel-2, Landsat, ASTER, ...) or hyperspectral
(EnMAP, PRISMA, EMIT, AVIRIS, ...). The only thing it needs from an image is the centre
wavelength (nm) of each band, plus the band width (FWHM) if known.

Input must be **surface reflectance** (atmospherically corrected), scaled to about 0-1.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from . import preprocess as pp
from .library import SpectralLibrary
from .sensors import Sensor, get_sensor, sensor_from_wavelengths, subset_sensor

PathLike = Union[str, Path]
# Strong atmospheric water-vapour absorption; surface reflectance is unreliable here.
DEFAULT_EXCLUDE: Tuple[Tuple[float, float], ...] = ((1340.0, 1460.0), (1790.0, 1990.0))
_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _numbers(text) -> np.ndarray:
    return np.array([float(x) for x in _NUM.findall(str(text))], dtype=float)


def _to_nm(values: np.ndarray, units_hint: str = "") -> np.ndarray:
    hint = units_hint.lower()
    if "micro" in hint or hint.strip() in {"um", "µm"}:
        return values * 1000.0
    if "nano" in hint or hint.strip() == "nm":
        return values
    return values * 1000.0 if np.nanmedian(values) < 50 else values  # looks like micrometres


# ---------------------------------------------------------------------------- Image
@dataclass
class Image:
    """A reflectance cube ``data[band, row, col]`` with band centres in nm. NaN = invalid pixel/band value."""

    data: np.ndarray
    wavelengths: np.ndarray
    fwhm: Optional[np.ndarray] = None
    band_names: Optional[List[str]] = None
    transform: object = None
    crs: object = None
    name: str = "image"
    _sensor: Optional[Sensor] = field(default=None, repr=False)

    def __post_init__(self):
        self.data = np.asarray(self.data, dtype=np.float32)
        self.wavelengths = np.asarray(self.wavelengths, dtype=float)
        if self.data.ndim != 3 or self.data.shape[0] != len(self.wavelengths):
            raise ValueError(f"data must be (bands, rows, cols) with {len(self.wavelengths)} bands, got {self.data.shape}")
        if self.fwhm is not None:
            self.fwhm = np.broadcast_to(np.asarray(self.fwhm, dtype=float), self.wavelengths.shape).copy()

    # ---- basics
    @property
    def n_bands(self) -> int:
        return self.data.shape[0]

    @property
    def rows(self) -> int:
        return self.data.shape[1]

    @property
    def cols(self) -> int:
        return self.data.shape[2]

    def __repr__(self) -> str:
        return (f"Image('{self.name}', {self.n_bands} bands, {self.rows}x{self.cols} px, "
                f"{self.wavelengths.min():.0f}-{self.wavelengths.max():.0f} nm)")

    @property
    def sensor(self) -> Sensor:
        """Band definition used to convolve the library to this image."""
        if self._sensor is not None:
            return self._sensor
        if self.fwhm is None and self.n_bands < 20:
            warnings.warn(
                "Band widths (fwhm) unknown for a multispectral image; assuming width = band spacing. "
                "Pass fwhm=..., or sensor=/band_names= for a known sensor.", stacklevel=2)
        return sensor_from_wavelengths(self.name, self.wavelengths, self.fwhm, self.band_names)

    # ---- construction
    @classmethod
    def from_array(
        cls, cube, wavelengths, fwhm=None, *, scale: float = 1.0, offset: float = 0.0,
        nodata: Optional[float] = None, valid_range: Optional[Tuple[float, float]] = (-0.05, 1.5),
        band_axis: int = 0, sensor=None, band_names: Optional[Sequence[str]] = None, **kw,
    ) -> "Image":
        """Wrap any array (from GEE, xarray, h5py, ...). Values become ``raw * scale + offset``."""
        a = np.moveaxis(np.asarray(cube, dtype=np.float32), band_axis, 0).copy()
        if nodata is not None:
            a[a == nodata] = np.nan
        a = a * np.float32(scale) + np.float32(offset)
        if valid_range is not None:
            a[(a < valid_range[0]) | (a > valid_range[1])] = np.nan
        sens = None
        if sensor is not None:
            if band_names is None:
                raise ValueError("band_names is required when sensor is given")
            sens = subset_sensor(sensor, band_names)
            wavelengths = sens.centers
            fwhm = sens.fwhms
        return cls(a, wavelengths, fwhm, list(band_names) if band_names is not None else None, _sensor=sens, **kw)

    @classmethod
    def read(
        cls, path: PathLike, *, sensor=None, band_names: Optional[Sequence[str]] = None,
        wavelengths=None, fwhm=None, scale: Optional[float] = None, offset: float = 0.0,
        nodata: Optional[float] = None, valid_range: Optional[Tuple[float, float]] = (-0.05, 1.5),
    ) -> "Image":
        """Read a GeoTIFF / ENVI / any GDAL raster (needs ``pip install rasterio``).

        Band wavelengths come from, in order: ``wavelengths=``; ``sensor=`` with ``band_names=``
        (the sensor band name of each file band, e.g. a Sentinel-2 export of B2,B3,B4,...);
        or the file's own metadata (ENVI ``wavelength``/``fwhm`` or per-band tags).
        ``scale``/``offset`` convert stored values to reflectance, e.g. ``scale=1e-4``
        (Sentinel-2 L2A) or ``scale=2.75e-5, offset=-0.2`` (Landsat Collection 2 Level-2).
        """
        try:
            import rasterio
        except ImportError as e:  # pragma: no cover
            raise ImportError("Reading images needs rasterio: pip install rasterio") from e

        with rasterio.open(path) as src:
            raw = src.read().astype(np.float32)
            nd = src.nodata if nodata is None else nodata
            transform, crs = src.transform, src.crs
            wl, fw = wavelengths, fwhm
            if wl is None and sensor is None:
                wl, fw_meta = _wavelengths_from_metadata(src)
                fw = fw if fw is not None else fw_meta
        if sensor is None and wl is None:
            raise ValueError(
                "Could not find band wavelengths in the file. Pass wavelengths=[...] (nm), or "
                "sensor='sentinel2a' with band_names=['B2','B3',...] in file order.")
        if scale is None:
            finite = raw[np.isfinite(raw)]
            if finite.size and np.percentile(finite, 99) > 5:
                raise ValueError(
                    "Values look like integers (for example 0-10000). Give scale=, e.g. scale=1e-4 for "
                    "Sentinel-2 L2A or scale=2.75e-5, offset=-0.2 for Landsat Collection 2.")
            scale = 1.0
        if wl is not None and len(np.atleast_1d(wl)) != raw.shape[0]:
            raise ValueError(f"{len(np.atleast_1d(wl))} wavelengths but the file has {raw.shape[0]} bands")
        return cls.from_array(
            raw, wl if wl is not None else [0.0] * raw.shape[0], fw, scale=scale, offset=offset, nodata=nd,
            valid_range=valid_range, sensor=sensor, band_names=band_names, transform=transform, crs=crs,
            name=Path(path).stem,
        )

    # ---- simple masks / indices
    def _band(self, nm: float, tol: float = 80.0) -> Optional[np.ndarray]:
        i = int(np.argmin(np.abs(self.wavelengths - nm)))
        return self.data[i] if abs(self.wavelengths[i] - nm) <= tol else None

    def normalized_difference(self, a_nm: float, b_nm: float) -> np.ndarray:
        a, b = self._band(a_nm), self._band(b_nm)
        if a is None or b is None:
            raise ValueError(f"Image has no bands near {a_nm} and {b_nm} nm")
        with np.errstate(invalid="ignore", divide="ignore"):
            return (a - b) / (a + b)

    def vegetation_mask(self, threshold: float = 0.4) -> np.ndarray:
        """True where NDVI (842 vs 665 nm) exceeds ``threshold``."""
        return np.nan_to_num(self.normalized_difference(842, 665), nan=-1.0) > threshold

    def water_mask(self, threshold: float = 0.3) -> np.ndarray:
        """True where NDWI (560 vs 842 nm) exceeds ``threshold``."""
        return np.nan_to_num(self.normalized_difference(560, 842), nan=-1.0) > threshold


def _wavelengths_from_metadata(src) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    n = src.count
    for ns in ("ENVI", None):
        tags = src.tags(ns=ns) if ns else src.tags()
        keys = {k.lower(): v for k, v in tags.items()}
        if "wavelength" in keys:
            wl = _numbers(keys["wavelength"])
            if len(wl) == n:
                units = keys.get("wavelength_units", "")
                fw = _numbers(keys["fwhm"]) if "fwhm" in keys else None
                wl_nm = _to_nm(wl, units)
                fw_nm = None if fw is None or len(fw) != n else fw * (wl_nm[0] / wl[0] if wl[0] else 1.0)
                return wl_nm, fw_nm
    centers, widths = [], []
    for i in range(1, n + 1):
        bt = {k.lower(): v for k, v in src.tags(i).items()}
        c = next((bt[k] for k in ("wavelength", "center_wavelength", "central_wavelength", "nominal_wavelength") if k in bt), None)
        w = next((bt[k] for k in ("fwhm", "bandwidth") if k in bt), None)
        if c is None:
            return None, None
        centers.append(_numbers(c)[0])
        if w is not None:
            widths.append(_numbers(w)[0])
    wl = _to_nm(np.array(centers), "")
    factor = wl[0] / centers[0] if centers[0] else 1.0
    return wl, (np.array(widths) * factor if len(widths) == n else None)


# ---------------------------------------------------------------------------- matching
@dataclass
class MatchResult:
    """Output of :func:`match_image`. All maps have shape (rows, cols)."""

    class_map: np.ndarray  # int32 index into ``labels``; -1 = invalid or no match under the angle limit
    angle_deg: np.ndarray  # float32 spectral angle to the best match (NaN if invalid)
    margin_deg: np.ndarray  # float32: second-best angle minus best angle (bigger = less ambiguous)
    labels: List[str]
    used_wavelengths: np.ndarray
    image: Image

    def counts(self) -> pd.DataFrame:
        """Pixels per class with mean angle and mean margin."""
        rows = []
        valid = self.class_map >= 0
        for i, lab in enumerate(self.labels):
            m = self.class_map == i
            if m.any():
                rows.append({"label": lab, "pixels": int(m.sum()), "percent_of_matched": 100.0 * m.sum() / max(valid.sum(), 1),
                             "mean_angle_deg": float(np.nanmean(self.angle_deg[m])), "mean_margin_deg": float(np.nanmean(self.margin_deg[m]))})
        df = pd.DataFrame(rows, columns=["label", "pixels", "percent_of_matched", "mean_angle_deg", "mean_margin_deg"])
        return df.sort_values("pixels", ascending=False).reset_index(drop=True)

    def names(self) -> np.ndarray:
        """Class name per pixel ('' where unmatched)."""
        lab = np.array(self.labels + [""], dtype=object)
        return lab[np.where(self.class_map >= 0, self.class_map, len(self.labels))]

    def to_geotiff(self, path: PathLike) -> Path:
        """Write class id, angle and margin as 3 bands (+ ``<name>_legend.csv`` with id -> label)."""
        try:
            import rasterio
        except ImportError as e:  # pragma: no cover
            raise ImportError("Writing GeoTIFF needs rasterio: pip install rasterio") from e
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        nodata = -9999.0
        stack = np.stack([
            np.where(self.class_map >= 0, self.class_map, nodata).astype(np.float32),
            np.nan_to_num(self.angle_deg, nan=nodata).astype(np.float32),
            np.nan_to_num(self.margin_deg, nan=nodata).astype(np.float32),
        ])
        with rasterio.open(path, "w", driver="GTiff", height=self.class_map.shape[0], width=self.class_map.shape[1],
                           count=3, dtype="float32", crs=self.image.crs, transform=self.image.transform, nodata=nodata) as dst:
            dst.write(stack)
            for i, d in enumerate(("class_id", "angle_deg", "margin_deg"), 1):
                dst.set_band_description(i, d)
        pd.DataFrame({"class_id": range(len(self.labels)), "label": self.labels}).to_csv(path.with_name(path.stem + "_legend.csv"), index=False)
        return path

    def plot(self, show: bool = True):  # pragma: no cover - needs a display
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
        cm = np.ma.masked_less(self.class_map, 0)
        im = ax[0].imshow(cm, cmap="tab20", interpolation="nearest", vmin=0, vmax=max(len(self.labels) - 1, 1))
        ax[0].set_title("best match")
        handles = [plt.Line2D([], [], marker="s", ls="", color=im.cmap(im.norm(i)), label=l) for i, l in enumerate(self.labels)]
        ax[0].legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(1.0, 1.0))
        for a, m, t in ((ax[1], self.angle_deg, "angle (deg), lower = better"), (ax[2], self.margin_deg, "margin (deg), higher = more certain")):
            p = a.imshow(m, cmap="viridis")
            a.set_title(t)
            fig.colorbar(p, ax=a, shrink=0.8)
        fig.tight_layout()
        if show:
            plt.show()
        return fig


def _range_mask(wl: np.ndarray, ranges) -> np.ndarray:
    m = np.zeros(wl.shape, bool)
    for lo, hi in ranges or ():
        m |= (wl >= lo) & (wl <= hi)
    return m


def match_image(
    image: Image,
    library: SpectralLibrary,
    group_by: Optional[str] = "material",
    max_angle_deg: Optional[float] = 10.0,
    exclude_nm: Sequence[Tuple[float, float]] = DEFAULT_EXCLUDE,
    wavelength_range_nm: Optional[Tuple[float, float]] = None,
    mask: Optional[np.ndarray] = None,
    mask_vegetation: Optional[float] = 0.4,
    mask_water: Optional[float] = None,
    min_band_fraction: float = 0.6,
    chunk: int = 4000,
) -> MatchResult:
    """Assign every pixel to the library material with the smallest spectral angle.

    Steps: (1) convolve the library to the image's bands, (2) drop unreliable bands
    (``exclude_nm``) and invalid pixels (NaN, ``mask``, vegetation/water), (3) spectral angle
    of each pixel to every library spectrum on the bands both have, (4) keep the best per
    ``group_by`` group (``"material"``, ``"chapter"``, or None for single spectra),
    (5) leave pixels unmatched when the best angle exceeds ``max_angle_deg``.

    Spectral angle ignores overall brightness, so illumination and albedo differences matter
    little; mixed pixels, vegetation and shadows still do, which is why masks are applied.
    """
    lib_b, _ = pp.to_sensor(library.wavelengths, library.X, image.sensor)  # (M, B)
    wl = image.wavelengths

    # ---- which bands to use
    use = np.isfinite(lib_b).mean(axis=0) >= 0.2
    use &= ~_range_mask(wl, exclude_nm)
    if wavelength_range_nm is not None:
        use &= (wl >= wavelength_range_nm[0]) & (wl <= wavelength_range_nm[1])
    if use.sum() < 3:
        raise ValueError("Fewer than 3 usable bands after exclusions; relax exclude_nm / wavelength_range_nm")

    # ---- which pixels to use
    valid = np.all(np.isfinite(image.data[use]), axis=0)
    if mask is not None:
        valid &= ~np.asarray(mask, bool)
    if mask_vegetation is not None:
        try:
            valid &= ~image.vegetation_mask(mask_vegetation)
        except ValueError:
            warnings.warn("No red/NIR bands for an NDVI vegetation mask; skipping it", stacklevel=2)
    if mask_water is not None:
        try:
            valid &= ~image.water_mask(mask_water)
        except ValueError:
            warnings.warn("No green/NIR bands for a water mask; skipping it", stacklevel=2)

    # ---- library side
    L = lib_b[:, use].astype(np.float32)
    V = np.isfinite(L)
    Lz = np.where(V, L, 0.0).astype(np.float32)
    Vf = V.astype(np.float32)
    l_norm2 = (Lz * Lz).sum(axis=1)
    enough = V.sum(axis=1) >= max(3, int(np.ceil(min_band_fraction * use.sum())))
    keep = enough & (l_norm2 > 0)
    if not keep.any():
        raise ValueError("No library spectrum covers enough of the image bands")
    Lz, Vf, l_norm2 = Lz[keep], Vf[keep], l_norm2[keep]
    meta = library.meta.iloc[np.where(keep)[0]]

    if group_by is None:
        keys = meta["name"].to_numpy()
    else:
        keys = meta[group_by].astype(str).to_numpy()
    labels, inv = np.unique(keys, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    sorted_inv = inv[order]
    starts = np.r_[0, np.where(np.diff(sorted_inv) != 0)[0] + 1]
    Lz_o, Vf_o, ln_o = Lz[order], Vf[order], l_norm2[order]
    n_groups = len(labels)

    # ---- pixel loop in chunks
    flat = image.data[use].reshape(use.sum(), -1).T  # (N, B')
    idx = np.where(valid.ravel())[0]
    class_flat = np.full(flat.shape[0], -1, dtype=np.int32)
    angle_flat = np.full(flat.shape[0], np.nan, dtype=np.float32)
    margin_flat = np.full(flat.shape[0], np.nan, dtype=np.float32)

    for s in range(0, len(idx), chunk):
        sel = idx[s:s + chunk]
        P = flat[sel]
        num = P @ Lz_o.T
        px2 = (P * P) @ Vf_o.T
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = num / np.sqrt(px2 * ln_o[None, :])
        ang = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
        ang[~np.isfinite(ang)] = np.inf
        g = np.minimum.reduceat(ang, starts, axis=1)  # best spectrum per group
        best = np.argmin(g, axis=1)
        rows = np.arange(len(sel))
        b_ang = g[rows, best]
        if n_groups > 1:
            g2 = g.copy()
            g2[rows, best] = np.inf
            second = g2.min(axis=1)
        else:
            second = np.full(len(sel), np.inf)
        class_flat[sel] = best
        angle_flat[sel] = b_ang
        margin_flat[sel] = np.where(np.isfinite(second), second - b_ang, np.nan)

    bad = ~np.isfinite(angle_flat)
    if max_angle_deg is not None:
        bad |= angle_flat > max_angle_deg
    class_flat[bad] = -1
    shape = (image.rows, image.cols)
    return MatchResult(class_flat.reshape(shape), angle_flat.reshape(shape), margin_flat.reshape(shape),
                       [str(x) for x in labels], wl[use], image)
