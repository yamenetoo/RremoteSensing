# usgs-splib07

**Download the USGS Spectral Library Version 7, turn it into a clean machine-learning-ready library, and preprocess spectra into features, in a few lines of Python.**

```python
from usgs_splib07 import download_splib07, build_library

root = download_splib07("data/")                                   # 1. download + extract
lib  = build_library(root, chapters="MSV", start=350, stop=2500, step=5)   # 2. one clean library
X    = lib.pipeline([("smooth", {}), ("to_sensor", {"sensor": "sentinel2a"})]).to_frame()  # 3. features
```

| You get | How |
|---|---|
| Resumable, verified download from USGS ScienceBase | `download_splib07()`, `splib07 download` |
| One library on a common wavelength grid, deleted channels kept as `NaN` | `build_library()` |
| NaN-aware preprocessing: resample, smooth, derivative, continuum removal, SNV / normalise | `SpectralLibrary` methods, `usgs_splib07.preprocess` |
| Convolution to Sentinel-2 or Landsat 8/9 bands (or your own sensor or SRF) | `to_sensor()`, `register_sensor()`, `convolve_srf()` |
| Indices, absorption depths, spectral-angle matching | `indices()`, `match()` |
| Save and reload without pickle | `save()`, `SpectralLibrary.load()` |

Works the same on Windows, Linux and macOS. No `D:\` paths, no CSV index files.

---

## Contents

1. [Install](#install)
2. [Quick start](#quick-start)
3. [How it works (flowchart)](#how-it-works)
4. [Concepts in five minutes](#concepts-in-five-minutes)
5. [API cheat sheet](#api-cheat-sheet)
6. [Command line](#command-line)
7. [Examples](#examples)
8. [Sensors](#sensors)
9. [Accuracy and limitations](#accuracy-and-limitations)
10. [Project layout and development](#project-layout-and-development)
11. [Citation](#citation)

---

## Install

```bash
cd USGS
pip install -e .                 # core: numpy, scipy, pandas, requests
pip install -e ".[progress]"     # + tqdm progress bar for downloads
pip install -e ".[plot]"         # + matplotlib (used by the example figure)
pip install -e ".[dev]"          # + pytest
```

Python 3.9 or newer. The package is imported as `usgs_splib07`; the command is `splib07`.

## Quick start

**1. Download.** The first command lists what ScienceBase offers, the second downloads and extracts it.

```bash
splib07 list-remote
splib07 download data/                 # prefers the smaller oversampled ASCII archive
splib07 download data/ --full          # or the full usgs_splib07.zip (about 5 GB)
```

**2. Build one library.**

```python
from usgs_splib07 import build_library

lib = build_library(
    "data/data",              # folder that contains ASCIIdata/
    library="splib07b",       # oversampled version (recommended)
    chapters="MSV",           # Minerals, Soils, Vegetation (None = all seven)
    kinds=("AREF",),          # absolute reflectance
    start=350, stop=2500, step=5,   # common grid in nm
)
print(lib)                    # SpectralLibrary(n=..., bands=431, 350-2500 nm, ...)
lib.meta.head()               # name, material, sample, chapter, family, kind, path
lib.save("splib07_vnir_swir.npz")
```

**3. Make features.**

```python
from usgs_splib07 import SpectralLibrary

lib = SpectralLibrary.load("splib07_vnir_swir.npz")

s2 = lib.pipeline([
    ("smooth", {"window": 11, "poly": 3}),
    ("to_sensor", {"sensor": "sentinel2a"}),      # 13 bands named B1 ... B12
    ("normalized", {"method": "l2"}),
])
X = s2.to_frame(include_meta=False)               # n x 13 feature table
y = s2.meta["chapter"]                            # labels for a classifier
```

Every method returns a **new** library and records itself in `lib.history`, so the original is never modified.

## How it works

Read the chart top to bottom: each row is one phase and arrows follow the data.

![Pipeline flowchart](docs/img/workflow-1.png)

The source of both charts is [`docs/workflow.tex`](docs/workflow.tex) (TikZ). Build it with `pdflatex docs/workflow.tex`, or open [`docs/workflow.pdf`](docs/workflow.pdf).

## Concepts in five minutes

The second chart follows **one spectrum** through the main steps.

![Journey of one spectrum](docs/img/workflow-2.png)

| Term | Meaning here |
|---|---|
| **Chapter** | The library is split into seven chapters: `M` minerals, `S` soils and mixtures, `C` coatings, `L` liquids, `O` organics, `A` artificial, `V` vegetation. Use `chapters="MV"` to choose. |
| **Kind** | `AREF` absolute reflectance (default, values around 0 to 1), `RREF` relative reflectance. Choose with `kinds=`. |
| **Spectrometer family** | `BECK` (0.2-3.0 um), `ASD` (0.35-2.5 um), `NIC` (FTIR, to about 216 um), `AVIRIS`. Each has its own wavelength file; the package matches it for you. |
| **Deleted channel** | USGS marks bad bands with `-1.23e34`. They become `NaN` and are never interpolated across, so no invented reflectance values appear in water-absorption bands. |
| **Common grid** | Spectra from different instruments are resampled (linear, no extrapolation) onto one grid so they fit in one matrix. Spectra covering less than 90% of the grid are dropped (for example FTIR on a VNIR-SWIR grid). |
| **Sensor convolution** | A multispectral band is a weighted average of the hyperspectral channels under its response curve. `to_sensor()` does that for Sentinel-2 and Landsat 8/9. |
| **Continuum removal** | Divide by the upper convex hull so absorption features become dips between 0 and 1. Good for comparing mineral features independent of overall brightness. |
| **Spectral angle (SAM)** | Angle between two spectra seen as vectors. Independent of brightness, so a darker pixel of the same material still matches. |

## API cheat sheet

**Build and load**

| Call | What it does |
|---|---|
| `download_splib07(dest)` | Download and extract; returns the folder to pass to `build_library`. |
| `list_remote_files()` | Files offered by ScienceBase (names, sizes, URLs). |
| `build_catalog(root, ...)` | DataFrame of spectrum files (no spectra read yet). |
| `build_library(root, ...)` | Read, resample and QC into a `SpectralLibrary`. |
| `SpectralLibrary.load(path)` / `.save(path)` | `.npz` round trip, no pickle. |

**`SpectralLibrary` methods** (each returns a new library)

| Method | What it does |
|---|---|
| `select(chapter="M", name_contains="calc")` | Subset by metadata or boolean mask. |
| `drop_invalid(min_valid_fraction)` / `clip(lo, hi)` | Quality control. |
| `resample(wavelengths, fwhm=None)` | New grid; `fwhm` gives Gaussian averaging for much coarser grids. |
| `to_sensor("sentinel2a")` | Convolve to sensor bands; columns get band names. |
| `smooth(window, poly)` / `derivative(order, window, poly)` | Savitzky-Golay, gaps preserved. |
| `continuum_removed()` / `snv()` / `normalized("l2")` | Shape features (`l2`, `max`, `minmax`, `area`). |
| `apply(fn, label)` | Your own step: `fn(wavelengths, X) -> X'`. |
| `pipeline([...])` | Run steps in order; each is a name or `(name, kwargs)`. |

**Outputs**

| Method | What it returns |
|---|---|
| `to_frame(include_meta=True)` | pandas DataFrame (metadata plus bands). |
| `indices(nd={...}, depths={...})` | Normalised differences like `{"ndvi": (842, 665)}` and absorption depths like `{"clay": (2120, 2205, 2260)}`. |
| `match(spectrum, k=5, query_wavelengths=None)` | Nearest library spectra by spectral angle (radians and degrees). |

Low-level functions (`resample`, `convolve_to_bands`, `convolve_srf`, `continuum_removal`, `spectral_angle`, ...) live in `usgs_splib07.preprocess` and work on plain NumPy arrays of shape `(n_spectra, n_bands)`.

## Command line

```bash
splib07 list-remote
splib07 download DEST [--full] [--pattern REGEX] [--no-extract]
splib07 build ROOT OUT.npz [--library splib07b] [--chapters MSV] [--kinds AREF|all] [--start 350 --stop 2500 --step 5]
splib07 info LIB.npz
splib07 features LIB.npz OUT.csv [--sensor sentinel2a] [--continuum] [--normalize l2]
```

## Examples

| File | What it shows | Needs internet |
|---|---|---|
| [`examples/01_synthetic_demo.py`](examples/01_synthetic_demo.py) | The whole pipeline on a tiny **synthetic** library: build, deleted-band handling, Sentinel-2 features, indices, spectral-angle matching, save and reload, figure. Runs in seconds. | No |
| [`examples/02_real_data.py`](examples/02_real_data.py) | Download the real library, build a VNIR-SWIR library, export a Sentinel-2 feature CSV, match a pixel. | Yes |

```bash
python examples/01_synthetic_demo.py
python examples/02_real_data.py data/
```

The synthetic demo matches a noisy, darker, coarser-sampled "pixel" to the right mineral:

```
Best matches for an unknown pixel (should be Kaolinite):
                       name  material chapter  angle_rad  angle_deg
 Kaolinite_KGa1_ASDFRb_AREF Kaolinite       M     0.0154     0.8818
Calcite_HS48.3B_ASDFRb_AREF   Calcite       M     0.0658     3.7686
  Grass_Dry_GR2_ASDFRa_AREF Grass_Dry       V     0.2417    13.8492
```

![Example output](docs/img/example_overview.png)

In panel 3, band `B10` is empty on purpose: its wavelength (about 1373 nm) falls in a deleted water-vapour band, so it stays `NaN` instead of being invented.

## Sensors

| Sensor name (aliases) | Bands | Response model |
|---|---|---|
| `sentinel2a` (`sentinel2`, `s2`) | B1 to B12 including B8A (13 bands) | Gaussian, nominal centre and width |
| `landsat8` (`landsat9`, `oli`, `l8`, `l9`) | B1 to B7 and B9 (8 bands) | Box, nominal band edges |

Add your own:

```python
from usgs_splib07 import Band, Sensor, register_sensor

register_sensor(Sensor("mycam", [Band("green", 550, 40), Band("red", 660, 40), Band("nir", 850, 60)]))
lib.to_sensor("mycam")
```

For an exact response curve use `usgs_splib07.preprocess.convolve_srf(wl, X, srf_wl, srf_resp)` (one band at a time).

## Accuracy and limitations

- **Approximate sensor responses.** Built-in bands use nominal centres and widths. Real responses are not Gaussian or box shaped. For exact values use `convolve_srf` with the official SRF, or use the USGS-provided convolved libraries (for example `s07SNTL2` for Sentinel-2).
- **Grid step.** Build with `step <= 5` nm before convolving to narrow bands (Sentinel-2 B5 and B6 are 15 nm wide). A warning is raised when the grid is too coarse.
- **Missing bands stay missing.** A sensor band is `NaN` when less than 80% of its response weight lies on valid channels.
- **No rescaling.** `AREF` values are already about 0 to 1. Small negative values from noise are kept unless you use `negative="nan"|"clip"` or `clip()`.
- **Download source.** File names and URLs are read from the ScienceBase JSON API at run time. If the preferred archive name (`ASCIIdata_splib07b`) is not offered, the full archive is used; run `splib07 list-remote` to see exactly what is available and pick one with `--pattern`.
- **Library versions.** `splib07a` is the original sampling, `splib07b` the oversampled version, `s07*` are libraries convolved to other instruments. Wavelength vectors are matched by channel count, so all of them can be read.

## Project layout and development

```
USGS/
├── pyproject.toml
├── README.md
├── src/usgs_splib07/
│   ├── download.py     ScienceBase listing, resumable download, safe extraction
│   ├── catalog.py      scan ASCIIdata, parse file names, read spectra, find wavelengths
│   ├── preprocess.py   NaN-aware resample, convolve, smooth, derivative, continuum, SAM, indices
│   ├── sensors.py      Sentinel-2 and Landsat definitions, sensor registry
│   ├── library.py      SpectralLibrary and build_library
│   └── cli.py          the `splib07` command
├── examples/           01_synthetic_demo.py, 02_real_data.py
├── docs/               workflow.tex (TikZ), workflow.pdf, img/
└── tests/              pytest suite (uses a local mock server for the download tests)
```

```bash
pip install -e ".[dev]"
pytest                          # library, preprocessing and download tests
cd docs && pdflatex workflow.tex   # rebuild the flowcharts
```

## Citation

If you use the data, cite:

Kokaly, R.F., Clark, R.N., Swayze, G.A., Livo, K.E., Hoefen, T.M., Pearson, N.C., Wise, R.A., Benzel, W.M., Lowers, H.A., Driscoll, R.L., and Klein, A.J., 2017, USGS Spectral Library Version 7: U.S. Geological Survey Data Series 1035, https://doi.org/10.3133/ds1035. Data release: https://doi.org/10.5066/F7RR1WDJ.
