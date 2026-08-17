# Jableh CA-Markov

Spatially explicit Markov-Cellular Automata modelling of land use/land
cover (LULC) change and directional prediction for **2030 in Jableh
District, Syrian Coastal Region**, using the Google Dynamic World
annual time series (2015-2026).

This repository accompanies the manuscript *"Spatially Explicit
Markov-CA Modelling of Land Use/Land Cover Change and Directional
Prediction for 2030 in Jableh District, Syrian Coastal Region, Using
Google Dynamic World Time-Series (2015-2026)"* and provides the
complete, reproducible source code for every table, figure, and
statistical result reported in the paper.

## What this package does

| Stage | Module | Status |
|---|---|---|
| Data acquisition (shapefile + Dynamic World download) | `lulc_toolkit` (external, see below) | Colab / GEE required |
| Annual class-area statistics | `statistics` (via `lulc_toolkit`) | Colab / GEE required |
| Seeded IPF/RAS transition-matrix estimation | `markov_ipf.py` | **Runs offline** |
| Anderson-Goodman stationarity test | `markov_ipf.py` | **Runs offline** |
| Pixel-level cross-tabulated transition matrix | `markov_ipf.py` | Requires real rasters |
| Markov forward projection & steady-state | `projection.py` | **Runs offline** |
| Monte Carlo bootstrap uncertainty | `uncertainty.py` | **Runs offline** |
| Classification-error perturbation | `uncertainty.py` | Requires real rasters + confusion matrix |
| Spatially explicit CA allocation (+ slope + road) | `ca_allocation.py` | Requires real rasters |
| Direction / hotspot analysis (sector, centroid, SDE, KDE) | `spatial_analysis.py` | Requires real rasters |
| Retrospective hindcasting (OA / Kappa / FoM) | `validation.py` | Requires real rasters |
| Seed-matrix sensitivity | `sensitivity.py` | **Runs offline** |
| CA-parameter sensitivity (D0, kernel size) | `sensitivity.py` | Requires real rasters |
| Logistic-regression / ANN benchmark CA | `benchmark.py` | Requires real rasters |
| Policy scenarios (green belt, forest protection, combined) | `scenarios.py` | Forest protection runs offline; green belt requires real rasters |
| PNG map export, Sentinel-2 basemap, Syria locator map | `mapping.py` | Colab / GEE / cartopy required |
| End-to-end orchestration | `pipeline.py` | `run_statistical_pipeline()` runs offline |

**"Runs offline" means the function only needs the annual class-area
time series (`Pivot_km2.csv`) -- no GEE credentials, no raster files,
no internet access required.** This covers the core Markov modelling,
stationarity testing, uncertainty quantification, seed sensitivity, and
the forest-protection policy scenario -- i.e. everything that does not
require pixel-level spatial data.

Everything else genuinely needs the real Jableh Dynamic World raster
stack (and, for the slope/road/benchmark/hindcasting additions, an
SRTM DEM and OSM road network) and is intended to run in the same
Google Colab environment used throughout the project.

## Installation

```bash
# Option A: pip, offline-capable subset only
pip install -e .

# Option B: pip, full stack (raster + GEE + mapping + benchmark)
pip install -e ".[all]"

# Option C: conda
conda env create -f environment.yml
conda activate jableh-ca-markov
```

## Quick start (offline statistical pipeline)

```python
from jableh_ca_markov.pipeline import load_pivot_csv, run_statistical_pipeline

areas = load_pivot_csv("data/processed/Pivot_km2.csv")
results = run_statistical_pipeline(areas, horizon_years=4, n_bootstrap=1000,
                                    output_dir="results/tables")

print(results["projection"])          # Table 6: Markov trajectory 2026-2030
print(results["stationarity"]["pooled_p"])   # Anderson-Goodman p-value
print(results["seed_sensitivity"])    # Table: seed-matrix sensitivity
print(results["forest_protection_projection"])  # Scenario 2 projection
```

## Full raster pipeline (Colab)

See `notebooks/01_full_pipeline.ipynb` for the cell-by-cell version
covering data download, PNG export, pixel-level transition mapping,
direction/hotspot analysis, the slope+road-enhanced CA allocation,
retrospective hindcasting, benchmark models, and cartographic map
export -- these steps require Google Earth Engine authentication and
should be run in Google Colab with Drive mounted.

## Repository structure

```
Jableh_CA_Markov/
├── README.md
├── requirements.txt
├── environment.yml
├── setup.py
├── data/
│   ├── raw/            # Dynamic World GeoTIFFs, SRTM DEM, OSM roads (not tracked in git)
│   └── processed/      # DynamicWorld_Statistics.csv, Pivot_km2.csv
├── notebooks/
│   └── 01_full_pipeline.ipynb
├── src/jableh_ca_markov/
│   ├── config.py
│   ├── markov_ipf.py
│   ├── projection.py
│   ├── ca_allocation.py
│   ├── spatial_analysis.py
│   ├── uncertainty.py
│   ├── validation.py
│   ├── sensitivity.py
│   ├── scenarios.py
│   ├── benchmark.py
│   ├── mapping.py
│   └── pipeline.py
├── results/
│   ├── figures/
│   └── tables/
└── tests/
    └── test_markov_ipf.py
```

## Data availability

Dynamic World source data are publicly available via Google Earth
Engine (`GOOGLE/DYNAMICWORLD/V1`); the Jableh administrative boundary
is publicly available via geoBoundaries
(<https://www.geoboundaries.org>). The Dynamic World acquisition and
PNG-export helper functions are provided by the companion
[`lulc_toolkit`](https://github.com/yamenetoo/RremoteSensing/tree/main/lulc_toolkit)
package.

## Citation

If you use this code, please cite the accompanying manuscript (details
to be added upon publication) and the underlying data sources:

- Brown, C.F. et al. (2022). Dynamic World, Near real-time global 10m
  land use land cover mapping. *Scientific Data*, 9, 251.
- Runfola, D. et al. (2020). geoBoundaries: A global database of
  political administrative boundaries. *PLOS ONE*, 15(4), e0231866.

## License

MIT License (see `LICENSE`).
