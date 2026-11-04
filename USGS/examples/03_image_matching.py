"""Match images to the library: multispectral (Sentinel-2) vs hyperspectral, on a SYNTHETIC scene.

Why this matters: Sentinel-2 has 13 broad bands, an imaging spectrometer has 200+ narrow ones.
Several minerals below (kaolinite / muscovite / alunite, calcite / dolomite) differ only by
narrow short-wave-infrared features. The same code runs on both; only the band list changes.

Nothing here is real data (see synthetic.py). It exercises the pipeline you would run on real
surface-reflectance images:
    img = Image.read("scene.tif", sensor="sentinel2a", band_names=[...], scale=1e-4)
    res = match_image(img, lib)

Run from the USGS folder:
    pip install -e ".[plot,geo]"
    python examples/03_image_matching.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from usgs_splib07 import match_image
from usgs_splib07.synthetic import demo_library, synthetic_scene


def accuracy_table(res, truth, labels):
    pred = res.names()
    true = np.array(labels, dtype=object)[truth]
    return {lab: float((pred[true == lab] == lab).mean()) for lab in labels}


def main() -> None:
    lib = demo_library(step=1.0)  # fine 1 nm grid so narrow bands convolve accurately
    sensors = {
        "Sentinel-2 (13 bands)": ("sentinel2a", None),
        "ASTER (9 bands)": ("aster", None),
        "Hyperspectral (206 bands, 10 nm)": (np.arange(400, 2451, 10.0), 10.0),
    }
    results = {}
    for title, (sensor, fwhm) in sensors.items():
        img, truth, labels = synthetic_scene(lib, sensor, fwhm=fwhm, noise=0.005, seed=11)
        res = match_image(img, lib)
        results[title] = (res, accuracy_table(res, truth, labels))
        overall = np.mean(res.names() == np.array(labels, dtype=object)[truth])
        print(f"{title:36s} overall accuracy: {overall:5.1%}")

    print("\nPer-material accuracy:")
    header = "".join(f"{t.split(' (')[0]:>14s}" for t in results)
    print(f"{'material':12s}{header}")
    for lab in labels:
        print(f"{lab:12s}" + "".join(f"{results[t][1][lab]:14.0%}" for t in results))

    try:
        figure(results, truth, labels)
    except ImportError:
        print("matplotlib not installed, skipping the figure")


def figure(results, truth, labels):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    cmap = plt.get_cmap("tab10")
    lookup = {lab: i for i, lab in enumerate(labels)}  # same colour for the same material everywhere
    n = len(results) + 1
    fig, ax = plt.subplots(1, n, figsize=(3.6 * n, 4.2))
    ax[0].imshow(truth, cmap=cmap, interpolation="nearest", vmin=0, vmax=9)
    ax[0].set_title("truth")
    for a, (title, (res, _)) in zip(ax[1:], results.items()):
        pred = np.array([lookup.get(x, -1) for x in res.names().ravel()]).reshape(truth.shape)
        a.imshow(np.ma.masked_less(pred, 0), cmap=cmap, interpolation="nearest", vmin=0, vmax=9)
        a.set_title(f"{title}\n{np.mean(pred == truth):.0%} correct", fontsize=9)
    for a in ax:
        a.set_xticks([]), a.set_yticks([])
    fig.legend(handles=[Patch(color=cmap(i / 9), label=lab) for i, lab in enumerate(labels)],
               loc="lower center", ncol=len(labels), fontsize=8, frameon=False)
    fig.suptitle("Same library, same code, only the band list changes (synthetic scene)", fontsize=10)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    target = Path(__file__).resolve().parents[1] / "docs" / "img" / "image_matching.png"
    fig.savefig(target, dpi=110)
    print(f"Figure written to {target}")


if __name__ == "__main__":
    main()
