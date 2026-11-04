# RremoteSensing

A collection of Python tools and reproducible research code for **remote sensing and land-cover analysis**, built mainly around Google Earth Engine (GEE), Sentinel-2, Google Dynamic World and the USGS Spectral Library. The repository grew out of work on land use / land cover (LULC) change in Syria and Iraq, and each folder is an independent project with its own dependencies, documentation and (where applicable) tests.

Maintained by **Mohamad Yamen Al-Mohamad**, Department of Statistics, University of Tabriz, Tabriz, Iran.

---

## Table of contents

1. [Repository map](#1-repository-map)
2. [Projects at a glance](#2-projects-at-a-glance)
3. [How the projects fit together](#3-how-the-projects-fit-together)
4. [Project details](#4-project-details)
   - [4.1 lulc_toolkit](#41-lulc_toolkit)
   - [4.2 jableh_ca_markov](#42-jableh_ca_markov)
   - [4.3 geedownload](#43-geedownload)
   - [4.4 USGS (usgs_splib07_processor)](#44-usgs-usgs_splib07_processor)
5. [Getting started](#5-getting-started)
6. [Requirements and accounts](#6-requirements-and-accounts)
7. [Data sources and licences](#7-data-sources-and-licences)
8. [Known issues and caveats](#8-known-issues-and-caveats)
9. [Citing](#9-citing)
10. [Contributing](#10-contributing)
11. [Author and contact](#11-author-and-contact)

---

## 1. Repository map

```
RremoteSensing/
├── README.md                         this file
│
├── lulc_toolkit/                     Python package: Dynamic World download, maps, statistics, charts
│   ├── src/lulc_toolkit/             auth, shapefile_utils, dynamic_world, maps, statistics, charts, io_utils
│   ├── examples/                     run_pipeline.py, tutorial_colab.ipynb
│   ├── tests/                        test_statistics.py
│   ├── pyproject.toml  requirements.txt  LICENSE  README.md
│
├── jableh_ca_markov/                 Python package: Markov-CA LULC change model, Jableh District (Syria)
│   ├── src/jableh_ca_markov/         config, markov_ipf, projection, uncertainty, sensitivity, scenarios,
│   │                                 ca_allocation, spatial_analysis, validation, benchmark, mapping, pipeline
│   ├── notebooks/01_full_pipeline.ipynb
│   ├── data/                         processed/Pivot_km2.csv  (raw/ for rasters, not tracked)
│   ├── results/                      tables/ (8 CSV result tables), figures/
│   ├── tests/test_markov_ipf.py
│   ├── setup.py  requirements.txt  environment.yml  CHANGELOG.md  LICENSE  README.md
│
├── geedownload/                      Python package + REST API: area search, GEE download of any satellite data, maps
│   ├── src/geedownload/              geocode, aoi, boundary, catalog, download, pipeline, maps, api, cli
│   ├── docs/FUNCTION_CATALOGUE.md    generated reference of every function, dataset, CLI command and endpoint
│   ├── tests/
│   ├── pyproject.toml  LICENSE  README.md
│
└── USGS/                             Python package: USGS Spectral Library v7 -> interpolation functions
    ├── usgs_splib07_processor/       core.py, builder.py, __init__.py
    ├── Chapter_1.csv ... Chapter_7.csv   index tables of the library (chapters 1-7)
    ├── pyproject.toml  requirements.txt  readme.md
```

## 2. Projects at a glance

| Folder | Purpose | Language / runtime | Needs GEE? | Version | Tests |
|---|---|---|---|---|---|
| `lulc_toolkit` | Download annual Dynamic World composites per district and year; render maps, area statistics and charts | Python ≥ 3.9, built for Colab | Yes | 0.1.0 (alpha) | `tests/test_statistics.py` |
| `jableh_ca_markov` | Markov chain + cellular-automata LULC change model and 2030 forecast for Jableh District | Python ≥ 3.10 | Only for the raster stages | 1.0.0 | `tests/test_markov_ipf.py` |
| `geedownload` | Search an area by name, save its shapefile, download any GEE satellite dataset (Sentinel, Landsat, MODIS, DEM ...), draw cartopy maps, serve a REST API | Python ≥ 3.9 | Yes | 0.2.0 | `tests/` |
| `USGS` | Turn USGS Splib07 spectra into callable reflectance functions `P_m(λ)` | Python ≥ 3.8 | No | 1.0.0 | – |

## 3. How the projects fit together

```
   shapefile of districts                  bounding box + dates
            │                                      │
            ▼                                      ▼
     lulc_toolkit  ──────────────┐        geedownload
  (Dynamic World per district    │        (any GEE dataset, maps, API)
   and year: maps, stats, charts)│
            │ Pivot_km2.csv      │ helper functions (acquisition, PNG export)
            ▼                    ▼
      jableh_ca_markov  (Markov / IPF transition matrices, CA allocation,
                         forecast to 2030, uncertainty, scenarios)

      USGS  (reference spectra as functions) — independent; used for spectral
            matching and unmixing against Sentinel-2 or other sensors
```

- `lulc_toolkit` produces the annual class-area table (`Pivot_km2.csv`) that `jableh_ca_markov` consumes, and `jableh_ca_markov/requirements.txt` installs `lulc_toolkit` straight from this repository (`git+https://github.com/yamenetoo/RremoteSensing.git#subdirectory=lulc_toolkit`).
- `geedownload` and `USGS` are stand-alone building blocks for spectral work.

---

## 4. Project details

### 4.1 lulc_toolkit

A **function-based toolkit** for downloading, mapping and analysing [Google Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) land cover **per administrative district and per year**, using Earth Engine and a shapefile. Written for Google Colab (shapefile read from Drive, outputs written to local Colab storage) but the core functions run in any environment with Earth Engine credentials.

**Features**

- Earth Engine authentication helper
- Read a shapefile archive (`.zip` or `.rar`) from Google Drive (Drive is mounted **read-only**)
- Download annual Dynamic World mode composites for every district and year
- Render every raster as a styled PNG map (boundary, graticule, legend, north arrow, scale bar)
- Per-class pixel counts and areas in m², ha and km²
- Charts: trend lines, stacked bars, province totals, percent change
- Zip and download any set of outputs

**Modules (`src/lulc_toolkit/`)**

| Module | Main contents |
|---|---|
| `auth` | `authenticate_ee()` |
| `shapefile_utils` | `mount_drive_readonly()`, `find_archive_in_drive()`, `extract_shapefile_archive()`, `load_shapefile()` |
| `dynamic_world` | `download_dynamicworld_for_years()`, class dictionaries `DW_CLASSES`, `DW_CLASS_NAMES` |
| `maps` | `make_lulc_png_map()`, `generate_all_maps()` |
| `statistics` | `compute_raster_stats()`, `build_statistics_table()`, `build_pivot_table()` |
| `charts` | `plot_trend_per_district()`, `plot_stacked_bar_per_year()`, `plot_province_total_trend()`, `plot_percent_change()`, `generate_all_charts()`, `DW_COLORS` |
| `io_utils` | `zip_and_download()` |

**Install**

```bash
pip install git+https://github.com/yamenetoo/RremoteSensing.git#subdirectory=lulc_toolkit
# Colab, only if your shapefile is a .rar archive:
apt-get install unrar -y -qq
```

**Quick start** (the same steps as `examples/run_pipeline.py`)

```python
from lulc_toolkit import (
    authenticate_ee, mount_drive_readonly, find_archive_in_drive,
    extract_shapefile_archive, load_shapefile, download_dynamicworld_for_years,
    DW_CLASSES, DW_CLASS_NAMES, generate_all_maps, build_statistics_table,
    build_pivot_table, generate_all_charts, zip_and_download,
)

authenticate_ee("your-ee-project-id")
mount_drive_readonly()
shp = extract_shapefile_archive(find_archive_in_drive("diyala"), "/content/shapefile_data")
gdf = load_shapefile(shp)

files, skipped = download_dynamicworld_for_years(
    gdf=gdf, name_field="ADM3_EN", years=[2014, 2019, 2024], out_dir="/content/DynamicWorld_Output")

maps   = generate_all_maps("/content/DynamicWorld_Output", "/content/DynamicWorld_Maps_PNG", DW_CLASSES)
stats  = build_statistics_table("/content/DynamicWorld_Output", DW_CLASS_NAMES,
                                "/content/DynamicWorld_Stats/DynamicWorld_Statistics.csv")
pivot  = build_pivot_table(stats, out_csv_path="/content/DynamicWorld_Stats/Pivot_km2.csv")
charts = generate_all_charts(stats, out_dir="/content/DynamicWorld_Charts")
zip_and_download(maps + charts, zip_path="/content/all_outputs.zip")
```

**Examples**: `examples/run_pipeline.py` (edit the `CONFIG` block: EE project id, archive search keyword, name field, years, output folders) and `examples/tutorial_colab.ipynb` (narrated notebook).

**Caveats**

- Dynamic World starts in mid-2015; earlier years are skipped and listed in the `skipped` return value instead of raising an error.
- Areas of lon/lat rasters use an approximate metres-per-degree factor at the raster's mean latitude. Good for comparisons; reproject to a local UTM CRS for survey-grade areas.
- `.rar` extraction needs the `unrar` command-line tool.
- Nothing is ever written back to Drive.

**Dependencies** (`pyproject.toml`): earthengine-api, geemap, geedim, geopandas, rasterio, numpy, pandas, matplotlib, matplotlib-scalebar; `pytest` for development. MIT licence.

---

### 4.2 jableh_ca_markov

Reproducible code for the manuscript **"Spatially Explicit Markov-CA Modelling of Land Use/Land Cover Change and Directional Prediction for 2030 in Jableh District, Syrian Coastal Region, Using Google Dynamic World Time-Series (2015–2026)"**. It reproduces every table, figure and statistical result of the paper.

**Pipeline stages and whether they run offline**

"Offline" means the stage needs only the annual class-area time series `data/processed/Pivot_km2.csv`: no GEE credentials, no rasters, no internet.

| Stage | Module | Needs |
|---|---|---|
| Data acquisition, annual class-area statistics | `lulc_toolkit` (see 4.1) | Colab + GEE |
| Seeded IPF/RAS transition-matrix estimation | `markov_ipf.py` | **offline** |
| Anderson–Goodman stationarity test | `markov_ipf.py` | **offline** |
| Pixel-level cross-tabulated transition matrix | `markov_ipf.py` | real rasters |
| Markov forward projection and steady state | `projection.py` | **offline** |
| Monte Carlo bootstrap uncertainty | `uncertainty.py` | **offline** |
| Classification-error perturbation | `uncertainty.py` | rasters + confusion matrix |
| Spatially explicit CA allocation (with slope and road effects) | `ca_allocation.py` | rasters, DEM, OSM roads |
| Direction / hotspot analysis (sector, centroid, standard deviational ellipse, KDE) | `spatial_analysis.py` | rasters |
| Retrospective hindcasting (OA, Kappa, FoM) | `validation.py` | rasters |
| Seed-matrix sensitivity | `sensitivity.py` | **offline** |
| CA-parameter sensitivity (D0, kernel size) | `sensitivity.py` | rasters |
| Logistic-regression / ANN benchmark CA | `benchmark.py` | rasters |
| Policy scenarios (green belt, forest protection, combined) | `scenarios.py` | forest protection offline; green belt needs rasters |
| PNG map export, Sentinel-2 basemap, Syria locator map | `mapping.py` | Colab / GEE / cartopy |
| End-to-end orchestration | `pipeline.py` | `run_statistical_pipeline()` runs offline |

`config.py` holds the class definitions and `build_seed_matrix()` (the domain-informed seed transition matrix).

**Install**

```bash
cd jableh_ca_markov
pip install -e .                 # offline-capable subset: numpy, pandas, scipy
pip install -e ".[all]"          # raster + GEE + benchmark + mapping + dev
# or
conda env create -f environment.yml && conda activate jableh-ca-markov
```

Optional extras: `raster` (rasterio, geopandas, shapely, richdem), `gee` (earthengine-api), `benchmark` (scikit-learn), `mapping` (matplotlib, cartopy, Pillow), `dev` (pytest). Python ≥ 3.10.

**Quick start (offline)**

```python
from jableh_ca_markov.pipeline import load_pivot_csv, run_statistical_pipeline

areas = load_pivot_csv("data/processed/Pivot_km2.csv")
res = run_statistical_pipeline(areas, horizon_years=4, n_bootstrap=1000, output_dir="results/tables")

res["projection"]                    # Markov trajectory 2026-2030
res["stationarity"]["pooled_p"]      # Anderson-Goodman p-value
res["seed_sensitivity"]              # seed-matrix sensitivity
res["forest_protection_projection"]  # Scenario 2
```

**Full raster pipeline** — `notebooks/01_full_pipeline.ipynb` (Colab, GEE authentication, Drive mounted): download, PNG export, pixel-level transitions, direction and hotspot analysis, slope+road-enhanced CA allocation, hindcasting, benchmark models, cartographic export.

**Provided results** (`results/tables/`): `P_annual.csv`, `markov_projection.csv`, `steady_state.csv`, `stationarity_per_class.csv`, `diagonal_dispersion.csv`, `monte_carlo_summary.csv`, `seed_sensitivity.csv`, `forest_protection_projection.csv`. `results/figures/` is the output folder for figures.

**Tests**: `pytest` runs `tests/test_markov_ipf.py` (IPF/RAS, seed-matrix and convergence behaviour).

**What changed in v1.0.0** (see `CHANGELOG.md`): two numerical problems found while writing the tests were fixed. (1) The seed matrix had a structural-zero column for `grass`, which IPF/RAS cannot repair; every class now has a small default reachability (`min_reachability = 0.02`) towards every other class. (2) Consecutive Dynamic World epochs have slightly different valid-pixel totals (up to about 2.7e-5 relative), which made IPF oscillate; `seeded_ipf()` now rescales the target marginal to the source total and checks convergence against both marginals directly. Effect on reported figures: less than 0.6 % on built-up, trees and crops (for example 2030 built-up 57.12 km² versus 57.19–57.43 km² in earlier drafts).

**Data**: Dynamic World via GEE (`GOOGLE/DYNAMICWORLD/V1`); administrative boundary from geoBoundaries. `data/raw/` (GeoTIFFs, SRTM DEM, OSM roads) is not tracked in git.

MIT licence.

---

### 4.3 geedownload

`geedownload` (v0.2.0) generalises the former `S2_Download_colab/S2.py` script. Besides Sentinel-2 it downloads **any Google Earth Engine satellite dataset** (Sentinel-1/2, Landsat 5/7/8/9, MODIS, SRTM and Copernicus DEM, WorldCover, Dynamic World, CHIRPS, ERA5-Land, ... or any asset id), finds the **area by name** (city, province or country), saves its **boundary as a shapefile**, draws **cartopy maps** (JPG: lat/lon grid, scale bar, north arrow, legend, country inset) and exposes everything as a **REST API** (FastAPI).

```python
import geedownload as gd
res = gd.download_area("Masyaf, Syria", "sentinel2", "2023-06-01", "2023-09-30",
                       out_dir="out", cloud_max=10, project="my-ee-project")
gd.plot_map(res.stack, "masyaf_rgb.jpg", area="Masyaf, Syria", bands=["B4", "B3", "B2"])
```

The old script's run is reproduced with `gd.download_area([42.35, 33.84, 42.55, 33.96], "sentinel2", "2023-06-01", "2023-09-30", bands="all", crs="EPSG:32637", scale=10)`. Large areas are tiled automatically. See [`geedownload/README.md`](geedownload/README.md) for the CLI and REST examples and [`geedownload/docs/FUNCTION_CATALOGUE.md`](geedownload/docs/FUNCTION_CATALOGUE.md) for every function. MIT licence.

---

### 4.4 USGS (usgs_splib07_processor)

Converts the **USGS Spectral Library Version 7** (Kokaly et al., 2017) into callable interpolation functions `P_m(λ)`, one per material, for spectral unmixing, matching against sensor bands and radiative-transfer work.

**What is in the folder**

- `usgs_splib07_processor/` — the package: `core.py` (`process_spectrum`, `create_material_interp_function`), `builder.py` (`build_material_library`, `load_material_library`).
- `Chapter_1.csv` … `Chapter_7.csv` — index tables of the library (material name plus paths of the reflectance and wavelength files). Chapters: 1 minerals, 2 soils and mixtures, 3 coatings, 4 liquids, 5 organics, 6 artificial materials, 7 vegetation.
- `pyproject.toml`, `requirements.txt` (numpy, pandas, matplotlib, scipy, tqdm), `readme.md`.

**Processing steps** (`process_spectrum` → `create_material_interp_function`)

1. Read name, reflectance path and wavelength path from an index row; rewrite the `D:\` prefix to `base_path`.
2. Load both files, trim `rng = 2` points from each end, drop negative reflectance values.
3. Normalise to 0–1 if the maximum exceeds 1 (percent data).
4. Sort wavelengths, convert units (µm → nm by default).
5. Return a `scipy.interpolate.interp1d` (linear, `fill_value = 0`, no bounds error).

`build_material_library()` runs this over all `*.csv` files in a folder with a progress bar and saves `{"name": [...], "fn": [...]}` to a pickle.

**Setup**

```bash
cd USGS
pip install -e .          # or: pip install -r requirements.txt
```

1. Download the full library (`usgs_splib07.zip`, about 5.1 GB): DOI <https://dx.doi.org/10.5066/F7RR1WDJ>, ScienceBase item `5807a2a2e4b0841e59e3a18d`, or <https://speclab.cr.usgs.gov/spectral-lib.html>, and extract it (for example to `D:\usgs_splib07\`).
2. Point the package at your copy with `base_path` (recommended), or edit the paths in the CSVs.

```python
from usgs_splib07_processor import build_material_library, load_material_library

build_material_library(
    csv_dir=r"D:\usgs_splib07\extracted_tables",
    output_path=r"D:\usgs_splib07\material_functions.pkl",
    base_path=r"D:\usgs_splib07",
    column_indices=[0, 2, 4],          # [name, reflectance_path, wavelength_path]
)

lib = load_material_library("material_functions.pkl")
P_m = lib["fn"][lib["name"].index("Calcite_HS188.3B")]
P_m(500.0)                              # reflectance at 500 nm
P_m([450, 550, 650])                    # vectorised
```

Library data citation: Kokaly, R.F., Clark, R.N., Swayze, G.A., et al. (2017). *USGS Spectral Library Version 7*, USGS Data Series 1035, <https://doi.org/10.3133/ds1035>.

---

## 5. Getting started

```bash
git clone https://github.com/yamenetoo/RremoteSensing.git
cd RremoteSensing
```

| I want to … | Start here |
|---|---|
| get annual land-cover maps and area tables per district | `lulc_toolkit` → `examples/run_pipeline.py` or `tutorial_colab.ipynb` |
| model and forecast land-cover change (Markov / CA) | `jableh_ca_markov` → offline quick start, then the Colab notebook |
| search an area by name and download satellite data (Sentinel, Landsat, MODIS, DEM ...) with maps | `geedownload` → `README.md` |
| use reference mineral / soil / vegetation spectra as functions | `USGS` |

## 6. Requirements and accounts

| Need | Used by | Notes |
|---|---|---|
| Python 3.8+ (3.9+ for `lulc_toolkit`, 3.10+ for `jableh_ca_markov`) | all | |
| Google Earth Engine account and a Cloud project id | `lulc_toolkit`, `geedownload`, GEE stages of `jableh_ca_markov` | `ee.Authenticate()` on first use |
| Google Colab and Google Drive | `lulc_toolkit`, the notebooks | `geedownload` also runs outside Colab |
| numpy, pandas, scipy | all | |
| geopandas, rasterio, shapely, richdem | raster stages | richdem for slope from a DEM |
| matplotlib, cartopy, Pillow, matplotlib-scalebar | maps and charts | |
| scikit-learn | benchmark CA | |
| `unrar` CLI | `.rar` shapefile archives | |
| USGS Splib07 download (~5.1 GB) | `USGS` | not included here |

## 7. Data sources and licences

| Data | Source | Used in |
|---|---|---|
| Dynamic World V1 | Google / WRI, `GOOGLE/DYNAMICWORLD/V1` (Brown et al., 2022) | `lulc_toolkit`, `jableh_ca_markov` |
| Sentinel-2 L2A Harmonized and other GEE datasets | ESA Copernicus, USGS, NASA ... via Google Earth Engine | `geedownload` |
| geoBoundaries | Runfola et al., 2020, <https://www.geoboundaries.org> | `jableh_ca_markov` |
| SRTM DEM, OSM roads | public sources (slope and road-distance layers) | `jableh_ca_markov` raster stages |
| USGS Spectral Library v7 | Kokaly et al., 2017 | `USGS` |

Code licence: **MIT** for `lulc_toolkit` and `jableh_ca_markov` (each has a `LICENSE` file) and declared as MIT in `USGS/pyproject.toml`. Check each data provider's terms before redistributing data.

## 8. Known issues and caveats

Recorded as found; none of these have been changed in the code.

- **Root README** was a placeholder (acknowledgements with `......`); this file replaces it.
- **`USGS`**: `process_spectrum()` rewrites paths by replacing the string `D:\` after `Path(...).resolve()`, so the path handling is Windows-specific; on Linux or macOS the library paths in the CSVs need to be edited or converted first. `pyproject.toml` says `readme = "README.md"` while the file is named `readme.md` (a problem on case-sensitive systems when building). Plot axes are labelled in µm, while interpolation functions take nm by default. The library itself (5 GB) is not in the repo.
- **`jableh_ca_markov`**: `setup.py` points to a separate repository URL (`yamenetoo/Jableh_CA_Markov`) although the project lives in this repo; `requirements.txt` mentions a `data_acquisition.py` that does not exist (acquisition is done through `lulc_toolkit`). Raster-based stages cannot be run from the repo alone because `data/raw/` is untracked.
- **`lulc_toolkit`**: `pyproject.toml` still has placeholder metadata (`Your Name`, `YOUR_USERNAME` URLs); the README's install line uses `github.com/yamenetoo/lulc-toolkit.git`, which is not this repo; use the `#subdirectory=lulc_toolkit` form above. `examples/run_pipeline.py` has the author's own EE project id and Diyala search keyword hard-coded in its `CONFIG`; change them.
- **Large files**: `USGS/Chapter_1.csv` is about 1.6 MB and the other chapters 15 KB – 485 KB; they are index tables only.

## 9. Citing

```
Al-Mohamad, M. Y. Spatially Explicit Markov-CA Modelling of Land Use/Land Cover Change and Directional
Prediction for 2030 in Jableh District, Syrian Coastal Region, Using Google Dynamic World Time-Series
(2015-2026). Manuscript (details to be added upon publication).
```

Please also cite the data and sources you use:

- Brown, C.F. et al. (2022). Dynamic World, Near real-time global 10 m land use land cover mapping. *Scientific Data* 9, 251.
- Runfola, D. et al. (2020). geoBoundaries: A global database of political administrative boundaries. *PLOS ONE* 15(4), e0231866.
- Kokaly, R.F. et al. (2017). USGS Spectral Library Version 7. U.S. Geological Survey Data Series 1035.

## 10. Contributing

Issues and pull requests are welcome.

1. Open an issue describing the problem or feature first.
2. Include a minimal reproducible example, with package versions, and the Earth Engine / Colab setup if relevant.
3. Add or update tests where a project has them (`pytest` in `lulc_toolkit` and `jableh_ca_markov`).
4. Keep projects self-contained: new tools go in their own folder with their own README and dependency list.

## 11. Author and contact

**Mohamad Yamen Al-Mohamad**
Department of Statistics, University of Tabriz, Tabriz, Iran
yamenmohamad@tabrizu.ac.ir · ORCID [0009-0009-1665-7203](https://orcid.org/0009-0009-1665-7203) · GitHub [@yamenetoo](https://github.com/yamenetoo)
