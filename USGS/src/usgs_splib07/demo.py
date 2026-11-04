"""A tiny SYNTHETIC library for offline examples and tests (NOT real USGS data).

The curves are simple Gaussian absorption features at textbook wavelengths. They exist so that
every function of the package can be tried in seconds without downloading anything.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .library import SpectralLibrary

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
    """A small SYNTHETIC library (8 invented materials) on a fine grid, default 1 nm. For offline demos and tests only."""
    nm = np.arange(start, stop + step / 2, step)
    curves = _curves(nm)
    X = np.vstack([curves[m] for m in MATERIALS])
    meta = pd.DataFrame({
        "name": [f"{m}_SYN1_ASDFRb_AREF" for m in MATERIALS],
        "material": MATERIALS,
        "sample": "SYN1",
        "chapter": ["V" if m == "Dry_Grass" else "M" for m in MATERIALS],
        "chapter_name": ["Vegetation" if m == "Dry_Grass" else "Minerals" for m in MATERIALS],
        "family": "ASD",
        "kind": "AREF",
    })
    return SpectralLibrary(nm, X, meta, None, ["synthetic"])
