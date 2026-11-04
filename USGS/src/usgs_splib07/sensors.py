"""Sensor band definitions used to convolve hyperspectral spectra to multispectral bands.

The band centres / widths below are nominal values (nm). Real spectral response
functions (SRFs) are not Gaussian or box shaped, so results are an approximation.
For exact work, supply the official SRF with :func:`usgs_splib07.preprocess.convolve_srf`,
or use the USGS-provided convolved libraries (for example ``s07SNTL2`` for Sentinel-2),
which were computed with the official SRFs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Band:
    name: str
    center: float  # nm
    fwhm: float  # nm
    shape: str = "gaussian"  # "gaussian" or "box"


@dataclass(frozen=True)
class Sensor:
    name: str
    bands: List[Band] = field(default_factory=list)

    @property
    def centers(self):
        return [b.center for b in self.bands]

    @property
    def fwhms(self):
        return [b.fwhm for b in self.bands]

    @property
    def names(self):
        return [b.name for b in self.bands]


def _s2a() -> Sensor:
    # Sentinel-2A MSI nominal centre wavelength / bandwidth (nm).
    spec = [
        ("B1", 442.7, 21), ("B2", 492.4, 66), ("B3", 559.8, 36), ("B4", 664.6, 31),
        ("B5", 704.1, 15), ("B6", 740.5, 15), ("B7", 782.8, 20), ("B8", 832.8, 106),
        ("B8A", 864.7, 21), ("B9", 945.1, 20), ("B10", 1373.5, 31), ("B11", 1613.7, 91),
        ("B12", 2202.4, 175),
    ]
    return Sensor("sentinel2a", [Band(n, c, w) for n, c, w in spec])


def _l8() -> Sensor:
    # Landsat 8/9 OLI nominal band edges (nm) -> centre and width, box shaped.
    edges = [
        ("B1", 435, 451), ("B2", 452, 512), ("B3", 533, 590), ("B4", 636, 673),
        ("B5", 851, 879), ("B6", 1566, 1651), ("B7", 2107, 2294), ("B9", 1363, 1384),
    ]
    return Sensor("landsat8", [Band(n, (a + b) / 2.0, float(b - a), "box") for n, a, b in edges])


def _aster() -> Sensor:
    # ASTER VNIR + SWIR nominal band edges (nm), box shaped. Very useful for clays, carbonates, alunite.
    edges = [
        ("B1", 520, 600), ("B2", 630, 690), ("B3N", 760, 860), ("B4", 1600, 1700),
        ("B5", 2145, 2185), ("B6", 2185, 2225), ("B7", 2235, 2285), ("B8", 2295, 2365), ("B9", 2360, 2430),
    ]
    return Sensor("aster", [Band(n, (a + b) / 2.0, float(b - a), "box") for n, a, b in edges])


def sensor_from_wavelengths(name, centers, fwhm=None, names=None, shape: str = "gaussian") -> Sensor:
    """Build a sensor from band centres (nm), e.g. read from a hyperspectral product's metadata.

    ``fwhm`` may be one number, one value per band, or None. When None the width of each
    band is taken as the local band spacing (a reasonable default for imaging spectrometers,
    but prefer the real FWHM from the product metadata when you have it).
    """
    import numpy as np

    c = np.asarray(centers, dtype=float)
    if c.ndim != 1 or c.size == 0:
        raise ValueError("centers must be a non-empty 1-D sequence")
    if fwhm is None:
        w = np.abs(np.gradient(c)) if c.size > 1 else np.array([10.0])
    else:
        w = np.broadcast_to(np.asarray(fwhm, dtype=float), c.shape)
    nm = list(names) if names is not None else [f"b{i + 1}" for i in range(c.size)]
    return Sensor(str(name), [Band(str(n), float(a), float(b), shape) for n, a, b in zip(nm, c, w)])


def subset_sensor(sensor, band_names) -> Sensor:
    """Keep only the named bands, in the given order (e.g. the bands of a Sentinel-2 GeoTIFF export)."""
    s = get_sensor(sensor)
    by_name = {b.name: b for b in s.bands}
    missing = [n for n in band_names if n not in by_name]
    if missing:
        raise KeyError(f"{s.name} has no bands {missing}. Available: {s.names}")
    return Sensor(s.name, [by_name[n] for n in band_names])


SENSORS: Dict[str, Sensor] = {}


def register_sensor(sensor: Sensor, *aliases: str) -> None:
    """Add a sensor definition (and optional aliases) to the registry."""
    SENSORS[sensor.name.lower()] = sensor
    for a in aliases:
        SENSORS[a.lower()] = sensor


def get_sensor(name_or_sensor) -> Sensor:
    """Look up a sensor by name or alias (``sentinel2a``, ``landsat8``, ``aster``, ...); a Sensor object is returned unchanged."""
    if isinstance(name_or_sensor, Sensor):
        return name_or_sensor
    key = str(name_or_sensor).lower()
    if key not in SENSORS:
        raise KeyError(f"Unknown sensor '{name_or_sensor}'. Available: {sorted(set(SENSORS))}")
    return SENSORS[key]


register_sensor(_s2a(), "sentinel2", "s2", "sentinel-2")
register_sensor(_l8(), "landsat9", "oli", "l8", "l9")
register_sensor(_aster())
