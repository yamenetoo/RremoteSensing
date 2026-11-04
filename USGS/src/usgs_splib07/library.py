"""The :class:`SpectralLibrary` container and the :func:`build_library` entry point."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from . import preprocess as pp
from .catalog import build_catalog, load_spectra
from .sensors import get_sensor

PathLike = Union[str, Path]


@dataclass
class SpectralLibrary:
    """Spectra on a common wavelength axis plus metadata.

    Attributes
    ----------
    wavelengths : (p,) nm (or band centres after :meth:`to_sensor`).
    X : (n, p) reflectance-like values; NaN = missing.
    meta : DataFrame with n rows (name, material, sample, chapter, spectrometer, ...).
    band_names : optional names for the columns (sensor bands).
    history : processing steps applied so far, in order.
    """

    wavelengths: np.ndarray
    X: np.ndarray
    meta: pd.DataFrame
    band_names: Optional[List[str]] = None
    history: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.wavelengths = np.asarray(self.wavelengths, float)
        self.X = np.asarray(self.X, float)
        if self.X.shape != (len(self.meta), len(self.wavelengths)):
            raise ValueError(f"Shape mismatch: X{self.X.shape}, meta {len(self.meta)}, wavelengths {len(self.wavelengths)}")
        self.meta = self.meta.reset_index(drop=True)

    # -------------------------------------------------------------- basics
    def __len__(self) -> int:
        return self.X.shape[0]

    @property
    def shape(self):
        return self.X.shape

    def __repr__(self) -> str:
        return (f"SpectralLibrary(n={len(self)}, bands={self.X.shape[1]}, "
                f"{self.wavelengths[0]:.0f}-{self.wavelengths[-1]:.0f} nm, steps={self.history})")

    def _new(self, X, wavelengths=None, band_names="keep", meta=None, label=None) -> "SpectralLibrary":
        return SpectralLibrary(
            self.wavelengths if wavelengths is None else wavelengths,
            X,
            self.meta if meta is None else meta,
            self.band_names if band_names == "keep" else band_names,
            self.history + ([label] if label else []),
        )

    # -------------------------------------------------------------- look up / inspect
    def search(self, text: str, column: str = "name") -> pd.DataFrame:
        """Rows whose ``column`` (default ``name``) contains ``text``, case-insensitive. The index is the row number."""
        hit = self.meta[column].astype(str).str.contains(str(text), case=False, regex=False)
        return self.meta[hit]

    def materials(self) -> pd.DataFrame:
        """One row per material: chapter and number of spectra, most spectra first."""
        cols = [c for c in ("chapter", "chapter_name") if c in self.meta.columns]
        out = self.meta.groupby(["material"] + cols).size().rename("n_spectra").reset_index()
        return out.sort_values(["n_spectra", "material"], ascending=[False, True]).reset_index(drop=True)

    def spectrum(self, which) -> np.ndarray:
        """One spectrum as a 1-D array on this library's wavelengths. ``which`` is a row number or an exact ``name``."""
        if isinstance(which, (int, np.integer)):
            return self.X[int(which)].copy()
        idx = np.flatnonzero(self.meta["name"].to_numpy() == which)
        if len(idx) == 0:
            near = self.search(str(which).split("_")[0])["name"].head(5).tolist()
            raise KeyError(f"No spectrum named {which!r}. Similar names: {near}")
        return self.X[idx[0]].copy()

    def plot(self, which=None, ax=None, max_n: int = 10, legend: bool = True):
        """Line plot of spectra (needs matplotlib). ``which``: row numbers / names, or text to search in names; default the first ``max_n``."""
        import matplotlib.pyplot as plt

        if which is None:
            rows = list(range(min(max_n, len(self))))
        elif isinstance(which, str):
            rows = list(self.search(which).index[:max_n])
        else:
            rows = [w if isinstance(w, (int, np.integer)) else int(np.flatnonzero(self.meta["name"].to_numpy() == w)[0]) for w in which]
        ax = ax or plt.subplots(figsize=(9, 4))[1]
        for r in rows:
            ax.plot(self.wavelengths, self.X[r], lw=1.2, label=str(self.meta["name"].iloc[r]))
        ax.set_xlabel("wavelength (nm)" if self.band_names is None else "band centre (nm)")
        ax.set_ylabel("reflectance")
        if legend and rows:
            ax.legend(fontsize=7, frameon=False)
        return ax

    # -------------------------------------------------------------- selection / QC
    def select(self, mask=None, **filters) -> "SpectralLibrary":
        """Subset by boolean mask or by metadata equality / membership.

        ``lib.select(chapter="M")``, ``lib.select(chapter=["M", "S"], family="ASD")``,
        ``lib.select(name_contains="calcite")`` (case-insensitive substring of ``name``).
        """
        m = np.ones(len(self), bool) if mask is None else np.asarray(mask, bool)
        for k, v in filters.items():
            if k == "name_contains":
                m &= self.meta["name"].str.contains(str(v), case=False, regex=False).to_numpy()
            else:
                vals = v if isinstance(v, (list, tuple, set)) else [v]
                m &= self.meta[k].isin(vals).to_numpy()
        return self._new(self.X[m], meta=self.meta[m])

    def drop_invalid(self, min_valid_fraction: float = 0.9) -> "SpectralLibrary":
        """Drop spectra with too many NaN channels."""
        frac = np.isfinite(self.X).mean(axis=1)
        return self.select(mask=frac >= min_valid_fraction)

    def clip(self, lo: Optional[float] = 0.0, hi: Optional[float] = None) -> "SpectralLibrary":
        """Limit values to ``[lo, hi]`` (default: remove negative noise)."""
        return self._new(np.clip(self.X, lo, hi), label=f"clip({lo},{hi})")

    # -------------------------------------------------------------- preprocessing
    def resample(self, wavelengths, fwhm: Optional[float] = None) -> "SpectralLibrary":
        """Interpolate onto a new wavelength grid in nm; optional ``fwhm`` smooths with a Gaussian of that width first."""
        wl = np.asarray(wavelengths, float)
        return self._new(pp.resample(self.wavelengths, self.X, wl, fwhm), wl, None, label=f"resample({wl[0]:.0f}-{wl[-1]:.0f},{len(wl)})")

    def to_sensor(self, sensor) -> "SpectralLibrary":
        """Convolve to a sensor's bands, e.g. ``lib.to_sensor("sentinel2a")``."""
        Xb, s = pp.to_sensor(self.wavelengths, self.X, sensor)
        return self._new(Xb, np.array(s.centers), s.names, label=f"to_sensor({s.name})")

    def smooth(self, window: int = 11, poly: int = 3) -> "SpectralLibrary":
        """Savitzky-Golay smoothing; ``window`` is in channels and must be odd."""
        return self._new(pp.smooth(self.wavelengths, self.X, window, poly), label=f"smooth({window},{poly})")

    def derivative(self, order: int = 1, window: int = 11, poly: int = 3) -> "SpectralLibrary":
        """Savitzky-Golay derivative with respect to wavelength (reflectance per nm^order)."""
        return self._new(pp.derivative(self.wavelengths, self.X, order, window, poly), label=f"derivative({order})")

    def continuum_removed(self) -> "SpectralLibrary":
        """Divide each spectrum by its upper convex hull, so absorption features become dips below 1."""
        return self._new(pp.continuum_removal(self.wavelengths, self.X), label="continuum_removal")

    def snv(self) -> "SpectralLibrary":
        """Standard normal variate: subtract each spectrum's mean and divide by its standard deviation."""
        return self._new(pp.snv(self.X), label="snv")

    def normalized(self, method: str = "l2") -> "SpectralLibrary":
        """Scale each spectrum: ``l2`` (unit length), ``max``, ``minmax`` or ``area``."""
        return self._new(pp.normalize(self.X, method), label=f"normalize({method})")

    def apply(self, fn: Callable[[np.ndarray, np.ndarray], np.ndarray], label: str = "custom") -> "SpectralLibrary":
        """Apply ``fn(wavelengths, X) -> X'`` (same shape) for custom preprocessing."""
        return self._new(fn(self.wavelengths, self.X), label=label)

    def pipeline(self, steps: Sequence) -> "SpectralLibrary":
        """Run steps in order. Each step is a method name or ``(name, kwargs)``.

        Example: ``lib.pipeline(["smooth", ("to_sensor", {"sensor": "sentinel2a"}), "snv"])``
        """
        lib = self
        for st in steps:
            name, kw = (st, {}) if isinstance(st, str) else st
            lib = getattr(lib, name)(**kw)
        return lib

    # -------------------------------------------------------------- features / analysis
    def indices(self, nd: Optional[dict] = None, depths: Optional[dict] = None) -> pd.DataFrame:
        """Spectral indices as columns.

        ``nd`` = {"ndvi": (842, 665)}; ``depths`` = {"clay_2200": (2120, 2200, 2250)}.
        """
        out = {}
        for k, (a, b) in (nd or {}).items():
            out[k] = pp.normalized_difference(self.wavelengths, self.X, a, b)
        for k, (l, c, r) in (depths or {}).items():
            out[k] = pp.band_depth(self.wavelengths, self.X, l, c, r)
        return pd.DataFrame(out, index=self.meta.index)

    def to_frame(self, include_meta: bool = True) -> pd.DataFrame:
        """DataFrame with one row per spectrum (metadata columns first, then one column per band)."""
        cols = self.band_names or [f"{w:.1f}" for w in self.wavelengths]
        spec = pd.DataFrame(self.X, columns=cols)
        return pd.concat([self.meta, spec], axis=1) if include_meta else spec

    def to_csv(self, path: PathLike, include_meta: bool = True) -> Path:
        """Write the library as a CSV (one row per spectrum, one column per band)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame(include_meta).to_csv(path, index=False)
        return path

    def match(self, query, k: int = 5, query_wavelengths=None) -> pd.DataFrame:
        """Top-``k`` library spectra closest to ``query`` by spectral angle.

        ``query`` is a vector on this library's grid, or (with ``query_wavelengths``)
        any grid, in which case it is resampled first.
        """
        q = np.asarray(query, float).ravel()
        if query_wavelengths is not None:
            q = pp.resample(np.asarray(query_wavelengths, float), q, self.wavelengths)[0]
        ang = pp.spectral_angle(self.X, q)
        order = np.argsort(np.where(np.isfinite(ang), ang, np.inf))[:k]
        res = self.meta.iloc[order][["name", "material", "chapter"]].copy()
        res["angle_rad"] = ang[order]
        res["angle_deg"] = np.degrees(ang[order])
        return res.reset_index(drop=True)

    # -------------------------------------------------------------- persistence (no pickle)
    def save(self, path: PathLike) -> Path:
        """Save to a compressed ``.npz`` (arrays + metadata JSON, loadable without pickle)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path, X=self.X, wavelengths=self.wavelengths,
            meta=np.array(self.meta.to_json(orient="split")),
            band_names=np.array(json.dumps(self.band_names)),
            history=np.array(json.dumps(self.history)),
        )
        return path if path.suffix == ".npz" else path.with_name(path.name + ".npz")

    @classmethod
    def load(cls, path: PathLike) -> "SpectralLibrary":
        """Load a library written by :meth:`save` (no pickle is used)."""
        from io import StringIO
        with np.load(path, allow_pickle=False) as z:
            meta = pd.read_json(StringIO(str(z["meta"])), orient="split")
            return cls(z["wavelengths"], z["X"], meta, json.loads(str(z["band_names"])), json.loads(str(z["history"])))


def build_library(
    root: PathLike,
    library: str = "splib07b",
    chapters: Optional[Sequence[str]] = None,
    kinds: Optional[Sequence[str]] = ("AREF",),
    families: Optional[Sequence[str]] = None,
    wavelengths: Optional[Sequence[float]] = None,
    start: float = 350.0,
    stop: float = 2500.0,
    step: float = 5.0,
    min_valid_fraction: float = 0.9,
    negative: str = "keep",
    workers: int = 8,
) -> SpectralLibrary:
    """Read the extracted USGS Splib07 ASCII data into one :class:`SpectralLibrary`.

    Every spectrum is resampled (linear, no extrapolation) onto a common grid, either
    ``wavelengths`` or ``start..stop`` every ``step`` nm. Spectra covering less than
    ``min_valid_fraction`` of the grid are dropped (this removes e.g. FTIR spectra when the
    grid is VNIR-SWIR). Deleted channels (-1.23e34) are NaN.

    ``negative``: ``"keep"`` leaves small negative values (noise), ``"nan"`` marks them
    missing, ``"clip"`` sets them to 0.
    """
    if negative not in {"keep", "nan", "clip"}:
        raise ValueError("negative must be 'keep', 'nan' or 'clip'")
    cat = build_catalog(root, library, chapters, kinds, families)
    cat, raw = load_spectra(cat, root, library, workers)
    grid = np.asarray(wavelengths, float) if wavelengths is not None else np.arange(start, stop + step / 2, step)

    X = np.vstack([pp.resample(r.wavelengths, r.values, grid)[0] for r in raw]) if raw else np.empty((0, len(grid)))
    if negative == "nan":
        X[X < 0] = np.nan
    elif negative == "clip":
        X = np.where(X < 0, 0.0, X)

    lib = SpectralLibrary(grid, X, cat, None, [f"build({library},{grid[0]:.0f}-{grid[-1]:.0f}nm)"])
    return lib.drop_invalid(min_valid_fraction)
