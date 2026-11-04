"""Offline demo: runs the whole pipeline on a small SYNTHETIC library.

No download needed. The spectra below are invented (Gaussian absorption features at
textbook wavelengths); they only imitate the file layout of the real USGS data, so you can
see every step working in a few seconds. For the real data see 02_real_data.py.

Run from the USGS folder:
    pip install -e ".[plot]"
    python examples/01_synthetic_demo.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from usgs_splib07 import SpectralLibrary, build_library

RNG = np.random.default_rng(7)
ASD_UM = np.linspace(0.35, 2.5, 2151)  # micrometres, like the real ASD files
NM = ASD_UM * 1000


def gauss(c, w, depth):
    return depth * np.exp(-0.5 * ((NM - c) / w) ** 2)


def spectra():
    """name -> (chapter folder, reflectance curve)"""
    kaolinite = 0.75 - gauss(2165, 12, 0.18) - gauss(2205, 12, 0.22) - gauss(1410, 15, 0.12) - gauss(1910, 25, 0.10)
    calcite = 0.80 - gauss(2340, 18, 0.30) - gauss(1870, 20, 0.05) - gauss(2160, 15, 0.04)
    hematite = 0.05 + 0.40 / (1 + np.exp(-(NM - 580) / 25)) - gauss(870, 60, 0.07) - gauss(1900, 40, 0.03)
    green = 0.04 + 0.46 / (1 + np.exp(-(NM - 710) / 14)) - gauss(670, 20, 0.03) - gauss(1450, 60, 0.30) - gauss(1940, 60, 0.35)
    green = np.where(NM > 1300, green * 0.8, green)
    dry = 0.10 + 0.35 / (1 + np.exp(-(NM - 650) / 90)) - gauss(2100, 80, 0.04) - gauss(1200, 50, 0.02)
    return {
        "Kaolinite_KGa1_ASDFRb_AREF": ("ChapterM_Minerals", kaolinite),
        "Calcite_HS48.3B_ASDFRb_AREF": ("ChapterM_Minerals", calcite),
        "Hematite_GDS27_ASDFRb_AREF": ("ChapterM_Minerals", hematite),
        "Grass_Green_GR1_ASDFRa_AREF": ("ChapterV_Vegetation", green),
        "Grass_Dry_GR2_ASDFRa_AREF": ("ChapterV_Vegetation", dry),
    }


def write_txt(path: Path, values, title="synthetic"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(title + "\n" + "\n".join(f"{v:.8e}" for v in values) + "\n")


def make_fake_usgs_tree(root: Path) -> None:
    lib = root / "ASCIIdata" / "ASCIIdata_splib07b"
    write_txt(lib / "splib07b_Wavelengths_ASD_0.35-2.5_microns_2151_ch.txt", ASD_UM)
    for name, (chapter, y) in spectra().items():
        y = y + RNG.normal(0, 0.004, y.size)  # instrument noise
        y = y.copy()
        y[(NM > 1350) & (NM < 1420)] = -1.23e34  # a "deleted" water-vapour band
        y[(NM > 1800) & (NM < 1950)] = -1.23e34
        write_txt(lib / chapter / f"splib07b_{name}.txt", y)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fake_usgs_tree(root)

        # 1) Build: catalog -> read -> common 5 nm grid -> QC
        lib = build_library(root, library="splib07b", start=350, stop=2500, step=5)
        print(lib, "\n")
        print(lib.meta[["name", "chapter_name", "family", "kind"]].to_string(index=False), "\n")

        # deleted channels stayed missing (they were NOT interpolated)
        calc = lib.select(name_contains="calcite").X[0]
        gap = (lib.wavelengths > 1360) & (lib.wavelengths < 1410)
        print(f"NaN channels inside the deleted 1350-1420 nm band: {np.isnan(calc[gap]).all()}\n")

        # 2) Preprocess for features, one pipeline call
        s2 = lib.pipeline([
            ("smooth", {"window": 11, "poly": 3}),
            ("to_sensor", {"sensor": "sentinel2a"}),
        ])
        print("Sentinel-2 band features (first 6 bands):")
        print(s2.to_frame().set_index("name").iloc[:, -13:-7].round(3).to_string(), "\n")

        # 3) Indices
        idx = lib.indices(
            nd={"ndvi_like": (842, 665)},
            depths={"kaolinite_2200": (2120, 2205, 2260), "carbonate_2340": (2250, 2340, 2400)},
        )
        print(idx.assign(name=lib.meta["name"]).set_index("name").round(3).to_string(), "\n")

        # 4) Match an unknown pixel (noisy, coarser, different wavelengths) with spectral angle
        true = spectra()["Kaolinite_KGa1_ASDFRb_AREF"][1]
        pixel_wl = np.arange(400, 2450, 20.0)
        pixel = np.interp(pixel_wl, NM, true) * 0.8 + RNG.normal(0, 0.01, pixel_wl.size)  # darker + noisy
        print("Best matches for an unknown pixel (should be Kaolinite):")
        print(lib.match(pixel, k=3, query_wavelengths=pixel_wl).round(4).to_string(index=False), "\n")

        # 5) Save and reload (no pickle)
        out = lib.save(Path(tmp) / "demo_library.npz")
        back = SpectralLibrary.load(out)
        print("Reloaded:", back)

        try:
            figure(lib, s2)
        except ImportError:
            print("matplotlib not installed, skipping the figure (pip install matplotlib)")


def figure(lib: SpectralLibrary, s2: SpectralLibrary) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    for x, n in zip(lib.X, lib.meta["material"]):
        ax[0].plot(lib.wavelengths, x, label=n)
    ax[0].set(title="1. Library on a common grid\n(gaps = deleted channels)", xlabel="wavelength (nm)", ylabel="reflectance")
    ax[0].legend(fontsize=8)

    cr = lib.continuum_removed()
    for x, n in zip(cr.X, cr.meta["material"]):
        if n in ("Kaolinite", "Calcite"):
            ax[1].plot(cr.wavelengths, x, label=n)
    ax[1].set(title="2. Continuum removal\n(absorption features become dips)", xlabel="wavelength (nm)", ylim=(0.6, 1.02))
    ax[1].legend(fontsize=8)

    for x, n in zip(s2.X, s2.meta["material"]):
        ax[2].plot(range(len(s2.band_names)), x, marker="o", label=n)
    ax[2].set_xticks(range(len(s2.band_names)), s2.band_names, rotation=60)
    ax[2].set(title="3. Sentinel-2 features\n(smooth then to_sensor)", xlabel="band")
    fig.tight_layout()
    target = Path(__file__).resolve().parents[1] / "docs" / "img" / "example_overview.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=110)
    print(f"Figure written to {target}")


if __name__ == "__main__":
    main()
