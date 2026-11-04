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


SENSORS: Dict[str, Sensor] = {}


def register_sensor(sensor: Sensor, *aliases: str) -> None:
    """Add a sensor definition (and optional aliases) to the registry."""
    SENSORS[sensor.name.lower()] = sensor
    for a in aliases:
        SENSORS[a.lower()] = sensor


def get_sensor(name_or_sensor) -> Sensor:
    if isinstance(name_or_sensor, Sensor):
        return name_or_sensor
    key = str(name_or_sensor).lower()
    if key not in SENSORS:
        raise KeyError(f"Unknown sensor '{name_or_sensor}'. Available: {sorted(set(SENSORS))}")
    return SENSORS[key]


register_sensor(_s2a(), "sentinel2", "s2", "sentinel-2")
register_sensor(_l8(), "landsat9", "oli", "l8", "l9")
