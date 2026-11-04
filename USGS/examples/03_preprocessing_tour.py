"""A tour of the preprocessing functions on the offline SYNTHETIC demo library (no download).

Run from the USGS folder:
    pip install -e ".[plot]"
    python examples/03_preprocessing_tour.py
"""
from pathlib import Path

import numpy as np

import usgs_splib07 as splib

lib = splib.demo_library(step=1.0).select(material=["Kaolinite", "Calcite", "Hematite"])
print(lib)

steps = {
    "original": lib,
    "smooth (Savitzky-Golay)": lib.smooth(window=31, poly=3),
    "continuum removed": lib.continuum_removed(),
    "first derivative": lib.smooth(31, 3).derivative(order=1, window=31),
    "Sentinel-2 bands": lib.to_sensor("sentinel2a"),
    "hyperspectral 10 nm": lib.to_sensor(splib.sensor_from_wavelengths("hs10", np.arange(400, 2451, 10.0), 10)),
}
for title, l in steps.items():
    print(f"{title:26s} {l.shape}  history={l.history}")

print("\nClay absorption depth near 2200 nm:")
print(lib.indices(depths={"clay_2200": (2120, 2200, 2250)}).assign(material=lib.meta["material"]).round(3).to_string(index=False))

print("\nWhich library spectrum is closest to a noisy calcite measurement?")
rng = np.random.default_rng(0)
query = lib.spectrum("Calcite_SYN1_ASDFRb_AREF") * 0.7 + rng.normal(0, 0.01, lib.shape[1])  # darker + noise
print(lib.match(query, k=3).round(3).to_string(index=False))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(14, 6.5))
    for ax, (title, l) in zip(axes.ravel(), steps.items()):
        l.plot(ax=ax, legend=False)
        ax.set_title(title, fontsize=10)
    axes[0, 0].legend([n.split("_")[0] for n in lib.meta["name"]], fontsize=8, frameon=False)
    fig.suptitle("Preprocessing tour (synthetic demo spectra)", fontsize=12)
    fig.tight_layout()
    out = Path(__file__).resolve().parents[1] / "docs" / "img" / "preprocessing.png"
    fig.savefig(out, dpi=110)
    print("Figure written to", out)
except ImportError:
    print("matplotlib not installed: figure skipped")
