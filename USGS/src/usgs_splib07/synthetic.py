"""Synthetic spectra and scenes for demos and tests (NOT real USGS data).

The curves are simple Gaussian absorption features at textbook wavelengths. They are only meant
to exercise the code and to show why narrow bands help: several of the minerals below differ
only by narrow SWIR features that a 13-band multispectral sensor cannot separate.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import preprocess as pp
from .imagery import Image
from .library import SpectralLibrary
from .sensors import Sensor, get_sensor, sensor_from_wavelengths

MATERIALS = ["Kaolinite", "Muscovite", "Alunite", "Calcite", "Dolomite", "Hematite", "Goethite", "Dry_Grass"]


def _curves(nm: np.ndarray) -> dict:
    g = lambda c, w, d: d * np.exp(-0.5 * ((nm - c) / w) ** 2)  # noqa: E731
    return {
        "Kaolinite": 0.75 - g(2165, 9, 0.18) - g(2205, 9, 0.22) - g(1410, 14, 0.12) - g(1910, 25, 0.10),
        "Muscovite": 0.72 - g(2200, 11, 0.20) - g(2250, 11, 0.08) - g(2350, 11, 0.10) - g(1410, 14, 0.06) - g(1910, 25, 0.08),
        "Alunite": 0.78 - g(2165, 9, 0.20) - g(1480, 14, 0.15) - g(1760, 12, 0.10) - g(2320, 12, 0.05),
        "Calcite": 0.80 - g(2340, 12, 0.30) - g(1870, 20, 0.05) - g(2155, 12, 0.04),
        "Dolomite": 0.78 - g(2320, 12, 0.30) - g(1890, 20, 0.04) - g(2150, 12, 0.03),
        "Hematite": 0.05 + 0.40 / (1 + np.exp(-(nm - 580) / 25)) - g(870, 60, 0.07) - g(1900, 40, 0.03),
        "Goethite": 0.06 + 0.38 / (1 + np.exp(-(nm - 560) / 30)) - g(930, 70, 0.10) - g(1900, 40, 0.03),
        "Dry_Grass": 0.10 + 0.35 / (1 + np.exp(-(nm - 650) / 90)) - g(2100, 80, 0.04) - g(1200, 50, 0.02),
    }


def demo_library(start: float = 350.0, stop: float = 2500.0, step: float = 1.0) -> SpectralLibrary:
    """A small synthetic library on a fine grid (default 1 nm)."""
    nm = np.arange(start, stop + step / 2, step)
    curves = _curves(nm)
    X = np.vstack([curves[m] for m in MATERIALS])
    meta = pd.DataFrame({
        "name": [f"{m}_SYN1_ASDFRb_AREF" for m in MATERIALS],
        "material": MATERIALS,
        "sample": "SYN1",
        "chapter": ["V" if m == "Dry_Grass" else "M" for m in MATERIALS],
        "family": "ASD",
        "kind": "AREF",
    })
    return SpectralLibrary(nm, X, meta, None, ["synthetic"])


def synthetic_scene(
    library: SpectralLibrary,
    sensor,
    *,
    fwhm=None,
    grid: Tuple[int, int] = (4, 2),
    block: int = 16,
    background: float = 0.25,
    max_background_fraction: float = 0.25,
    noise: float = 0.005,
    seed: int = 0,
) -> Tuple[Image, np.ndarray, List[str]]:
    """Build a tiled scene: one block per library material, each pixel a noisy mixture.

    ``sensor`` is a sensor name/Sensor, or a sequence of band centres in nm (hyperspectral).
    Returns ``(image, truth, labels)`` where ``truth[row, col]`` indexes ``labels``.
    """
    rng = np.random.default_rng(seed)
    if isinstance(sensor, (str, Sensor)):
        s = get_sensor(sensor)
    else:
        s = sensor_from_wavelengths("synthetic_hyperspectral", sensor, fwhm)
    Xs = pp.convolve_to_bands(library.wavelengths, library.X, s.centers, s.fwhms, [b.shape for b in s.bands])
    labels = list(library.meta["material"])
    n = len(labels)
    gr, gc = grid
    if gr * gc < n:
        raise ValueError("grid has fewer blocks than library materials")
    rows, cols = gr * block, gc * block
    truth = np.full((rows, cols), -1, dtype=np.int32)
    cube = np.full((len(s.centers), rows, cols), np.nan, dtype=np.float32)
    for k in range(n):
        r0, c0 = (k // gc) * block, (k % gc) * block
        truth[r0:r0 + block, c0:c0 + block] = k
        for r in range(block):
            for c in range(block):
                f = rng.uniform(0, max_background_fraction)
                brightness = rng.uniform(0.7, 1.05)
                px = ((1 - f) * Xs[k] + f * background) * brightness + rng.normal(0, noise, Xs.shape[1])
                cube[:, r0 + r, c0 + c] = px
    img = Image(cube, s.centers, s.fwhms, s.names, name=s.name, _sensor=s)
    return img, truth, labels
