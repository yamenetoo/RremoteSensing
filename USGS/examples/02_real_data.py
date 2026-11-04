"""Real-data workflow: download -> build -> Sentinel-2 features -> match a pixel.

Run from the USGS folder:
    pip install -e ".[progress]"
    python examples/02_real_data.py data/

The first run downloads the library from USGS ScienceBase (the oversampled ASCII archive
if available, otherwise the full ~5 GB zip), so it needs internet access. Re-running is cheap:
the download resumes/skips and the built library is cached in ``<dest>/splib07_vnir_swir.npz``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from usgs_splib07 import SpectralLibrary, build_library, download_splib07


def main(dest: str = "data") -> None:
    dest_p = Path(dest)
    cache = dest_p / "splib07_vnir_swir.npz"

    if cache.exists():
        lib = SpectralLibrary.load(cache)
        print("Loaded cached library:", lib)
    else:
        root = download_splib07(dest_p)  # step 1: download + extract
        lib = build_library(  # step 2: build on a 5 nm VNIR-SWIR grid
            root, library="splib07b", chapters="MSV", kinds=("AREF",), start=350, stop=2500, step=5
        )
        lib.save(cache)
        print("Built:", lib)

    # step 3: features for a classifier (Sentinel-2 bands, normalised shape)
    s2 = lib.pipeline([
        ("smooth", {"window": 11, "poly": 3}),
        ("to_sensor", {"sensor": "sentinel2a"}),
        ("normalized", {"method": "l2"}),
    ])
    table = s2.to_frame()  # metadata + B1..B12
    table.to_csv(dest_p / "splib07_sentinel2_features.csv", index=False)
    print(f"Feature table: {table.shape[0]} spectra x {len(s2.band_names)} bands")
    print(table.groupby("chapter_name").size().to_string())

    # step 4: spectral-angle matching of a (here: made-up) 13-band Sentinel-2 pixel
    sensor_lib = lib.to_sensor("sentinel2a")
    pixel = np.nanmedian(sensor_lib.select(chapter="V").X, axis=0)  # stand-in: median vegetation spectrum
    print("\nClosest library spectra to the pixel:")
    print(sensor_lib.match(pixel, k=5).round(4).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
