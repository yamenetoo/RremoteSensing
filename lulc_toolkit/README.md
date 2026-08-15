# lulc-toolkit

A function-based Python toolkit for downloading, mapping, and analyzing
[Google Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
land-use/land-cover (LULC) data **per administrative district, per year**,
using Google Earth Engine and a local shapefile.

Built for use in Google Colab (shapefile read from Google Drive, all
outputs written to local Colab storage), but the core functions work in
any Python environment with Earth Engine credentials configured.

## Features

- 🔑 Earth Engine authentication helper
- 📂 Read a shapefile archive (`.zip`/`.rar`) from Google Drive — **read-only**
- 🛰️ Download annual Dynamic World mode-composites per district, per year
- 🗺️ Render each raster as a styled PNG map (boundary, graticule, legend,
  north arrow, scale bar)
- 📊 Compute per-class pixel-count and area statistics (m² / ha / km²)
- 📈 Generate comparison charts (trend lines, stacked bars, province
  totals, percent change)
- 📦 Zip and download any set of outputs

## Installation

```bash
pip install git+https://github.com/YOUR_USERNAME/lulc-toolkit.git
```

Or, in a Colab cell:

```python
!pip install -q git+https://github.com/YOUR_USERNAME/lulc-toolkit.git
!apt-get install unrar -y -qq   # only needed if your shapefile is a .rar archive
```

## Quick start

```python
import ee
from lulc_toolkit import (
    authenticate_ee, mount_drive_readonly, find_archive_in_drive,
    extract_shapefile_archive, load_shapefile,
    download_dynamicworld_for_years, DW_CLASSES, DW_CLASS_NAMES,
    generate_all_maps, build_statistics_table, build_pivot_table,
    generate_all_charts, zip_and_download,
)

# 1. Authenticate Earth Engine
authenticate_ee("your-ee-project-id")

# 2. Locate & load your shapefile (read-only access to Drive)
mount_drive_readonly()
archive_path = find_archive_in_drive("diyala")           # matches e.g. diyala_shapefile.rar
shp_path = extract_shapefile_archive(archive_path, "/content/shapefile_data")
gdf = load_shapefile(shp_path)

# 3. Download Dynamic World composites for each district x year
files, skipped = download_dynamicworld_for_years(
    gdf=gdf,
    name_field="ADM3_EN",
    years=[2014, 2019, 2024],
    out_dir="/content/DynamicWorld_Output",
)

# 4. Render PNG maps
maps = generate_all_maps(
    in_dir="/content/DynamicWorld_Output",
    out_dir="/content/DynamicWorld_Maps_PNG",
    class_dict=DW_CLASSES,
)

# 5. Compute statistics
stats_df = build_statistics_table(
    in_dir="/content/DynamicWorld_Output",
    class_names=DW_CLASS_NAMES,
    out_csv_path="/content/DynamicWorld_Stats/DynamicWorld_Statistics.csv",
)
pivot_df = build_pivot_table(
    stats_df, out_csv_path="/content/DynamicWorld_Stats/Pivot_km2.csv"
)

# 6. Generate charts
charts = generate_all_charts(stats_df, out_dir="/content/DynamicWorld_Charts")

# 7. Package everything and download it
zip_and_download(maps + charts, zip_path="/content/all_outputs.zip")
```

See [`examples/run_pipeline.py`](examples/run_pipeline.py) for a complete
runnable script, and
[`examples/tutorial_colab.ipynb`](examples/tutorial_colab.ipynb) for a
narrated, cell-by-cell Colab notebook.

## Module overview

| Module | Contents |
|---|---|
| `lulc_toolkit.auth` | `authenticate_ee()` |
| `lulc_toolkit.shapefile_utils` | `mount_drive_readonly()`, `find_archive_in_drive()`, `extract_shapefile_archive()`, `load_shapefile()` |
| `lulc_toolkit.io_utils` | `zip_and_download()` |
| `lulc_toolkit.dynamic_world` | `download_dynamicworld_for_years()`, `DW_CLASSES`, `DW_CLASS_NAMES` |
| `lulc_toolkit.maps` | `make_lulc_png_map()`, `generate_all_maps()` |
| `lulc_toolkit.statistics` | `compute_raster_stats()`, `build_statistics_table()`, `build_pivot_table()` |
| `lulc_toolkit.charts` | `plot_trend_per_district()`, `plot_stacked_bar_per_year()`, `plot_province_total_trend()`, `plot_percent_change()`, `generate_all_charts()`, `DW_COLORS` |

## Notes & caveats

- **Dynamic World coverage** starts in mid-2015. Requesting an earlier
  year is handled gracefully (skipped, and reported in the `skipped`
  return value) rather than raising an error.
- **Area calculations** for geographic (lon/lat) rasters use an
  approximation of meters-per-degree at each raster's mean latitude.
  This is accurate enough for comparative analysis; for survey-grade
  area accuracy, reproject to a local UTM CRS first.
- **`.rar` extraction** requires the `unrar` CLI tool to be installed on
  the system (`apt-get install unrar` on Debian/Ubuntu/Colab).
- All output paths in the examples point at `/content/...` (Colab local
  storage). Drive is only ever mounted **read-only**, to locate the
  input shapefile — no outputs are written back to Drive by this
  package.

## Development

```bash
git clone https://github.com/YOUR_USERNAME/lulc-toolkit.git
cd lulc-toolkit
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
