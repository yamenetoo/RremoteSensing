# usgs-splib07

Download the **USGS Spectral Library Version 7**, build a clean spectral library on a common
wavelength grid, and preprocess spectra into features (resampling, sensor-band convolution,
smoothing, derivatives, continuum removal, normalisation, indices, spectral-angle matching).

Cross-platform (no `D:\` paths), no pickle files, NaN-aware throughout.

## Install

```bash
pip install -e .            # from this folder
pip install -e ".[progress]"  # optional tqdm progress bar
```

## 1. Download

```bash
splib07 list-remote                 # see what ScienceBase offers (names + sizes)
splib07 download data/              # smaller oversampled ASCII archive (ASCIIdata_splib07b)
splib07 download data/ --full       # full usgs_splib07.zip (~5 GB)
splib07 download data/ --pattern "ASCIIdata_splib07a"   # any other archive by regex
```

Downloads resume after interruption, are verified by size (and checksum if ScienceBase gives one),
and extraction rejects unsafe paths. Python: `download_splib07("data/")`.

## 2. Build a library

```python
from usgs_splib07 import build_library

lib = build_library("data/data", library="splib07b",
                    chapters="MSV",            # minerals, soils, vegetation (None = all)
                    kinds=("AREF",),           # absolute reflectance
                    start=350, stop=2500, step=5)   # common grid, nm
print(lib)            # SpectralLibrary(n=..., bands=431, 350-2500 nm, ...)
lib.meta.head()       # name, material, sample, chapter, family, kind, path
lib.save("splib07_vnir_swir.npz")
```

Deleted channels (`-1.23e34`) become NaN and are **not** interpolated across. Spectra that do not cover
at least `min_valid_fraction` (0.9) of the grid are dropped (for example FTIR spectra on a VNIR-SWIR grid).

## 3. Preprocess for features

```python
from usgs_splib07 import SpectralLibrary
lib = SpectralLibrary.load("splib07_vnir_swir.npz")

s2 = lib.pipeline([
    ("clip", {"lo": 0.0, "hi": 1.0}),
    ("smooth", {"window": 11, "poly": 3}),
    ("to_sensor", {"sensor": "sentinel2a"}),     # 13 bands, names B1..B12
    ("normalized", {"method": "l2"}),
])
X = s2.to_frame(include_meta=False)     # n x 13 feature table
y = s2.meta["chapter"]                  # labels

lib.continuum_removed()                 # absorption features
lib.derivative(order=1)                 # 1st derivative
lib.indices(nd={"ndvi": (842, 665)}, depths={"carb_2340": (2250, 2340, 2400)})
lib.select(chapter="M", name_contains="calcite")
lib.match(pixel_spectrum, k=5, query_wavelengths=wl)   # spectral-angle nearest spectra
```

Every method returns a new library and records itself in `lib.history`.
Custom steps: `lib.apply(lambda wl, X: ..., label="mine")`.

CLI equivalents: `splib07 build data/data lib.npz --chapters MSV`,
`splib07 info lib.npz`, `splib07 features lib.npz s2.csv --sensor sentinel2a --continuum`.

## Notes on accuracy

- Built-in sensors (`sentinel2a`, `landsat8`/`landsat9`) use nominal centre/width values with a Gaussian
  (Sentinel-2) or box (Landsat) response. Real SRFs differ. For exact results use
  `preprocess.convolve_srf(wl, X, srf_wl, srf_resp)` with the official SRF, or use the USGS convolved
  libraries (for example `s07SNTL2` for Sentinel-2) that were computed with official SRFs.
- Build with `step <= 5` nm before convolving to narrow bands (Sentinel-2 B5/B6: 15 nm).
- Reflectance is not rescaled; AREF values are already 0-1. Use `clip` if you want to bound noise.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

## Data citation

Kokaly, R.F., Clark, R.N., Swayze, G.A., Livo, K.E., Hoefen, T.M., Pearson, N.C., Wise, R.A.,
Benzel, W.M., Lowers, H.A., Driscoll, R.L., and Klein, A.J., 2017, USGS Spectral Library Version 7:
U.S. Geological Survey Data Series 1035, https://doi.org/10.3133/ds1035
(data release: https://doi.org/10.5066/F7RR1WDJ).
