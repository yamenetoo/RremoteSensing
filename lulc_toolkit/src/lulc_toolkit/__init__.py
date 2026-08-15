"""
lulc_toolkit
============

A function-based toolkit for downloading, mapping, and analyzing
Google Dynamic World (GOOGLE/DYNAMICWORLD/V1) land-use/land-cover data
per administrative district, for one or more years, using Google Earth
Engine + a local shapefile.

Typical usage
-------------
>>> import ee
>>> from lulc_toolkit import (
...     authenticate_ee, mount_drive_readonly, find_archive_in_drive,
...     extract_shapefile_archive, load_shapefile,
...     download_dynamicworld_for_years, DW_CLASSES,
...     generate_all_maps, build_statistics_table, build_pivot_table,
...     generate_all_charts, zip_and_download,
... )
>>>
>>> authenticate_ee("my-ee-project")
>>> mount_drive_readonly()
>>> archive = find_archive_in_drive("diyala")
>>> shp_path = extract_shapefile_archive(archive, "/content/shapefile_data")
>>> gdf = load_shapefile(shp_path)
>>> files, skipped = download_dynamicworld_for_years(
...     gdf, name_field="ADM3_EN", years=[2014, 2019, 2024],
...     out_dir="/content/DynamicWorld_Output",
... )

See the ``examples/`` folder for a full end-to-end script and a
ready-to-run Colab tutorial notebook.
"""

from .auth import authenticate_ee
from .shapefile_utils import (
    mount_drive_readonly,
    find_archive_in_drive,
    extract_shapefile_archive,
    load_shapefile,
)
from .io_utils import zip_and_download
from .dynamic_world import (
    DW_CLASSES,
    DW_CLASS_NAMES,
    download_dynamicworld_for_years,
)
from .maps import make_lulc_png_map, generate_all_maps
from .statistics import (
    parse_tif_filename,
    compute_raster_stats,
    build_statistics_table,
    build_pivot_table,
)
from .charts import (
    DW_COLORS,
    plot_trend_per_district,
    plot_stacked_bar_per_year,
    plot_province_total_trend,
    plot_percent_change,
    generate_all_charts,
)

__version__ = "0.1.0"

__all__ = [
    "authenticate_ee",
    "mount_drive_readonly",
    "find_archive_in_drive",
    "extract_shapefile_archive",
    "load_shapefile",
    "zip_and_download",
    "DW_CLASSES",
    "DW_CLASS_NAMES",
    "download_dynamicworld_for_years",
    "make_lulc_png_map",
    "generate_all_maps",
    "parse_tif_filename",
    "compute_raster_stats",
    "build_statistics_table",
    "build_pivot_table",
    "DW_COLORS",
    "plot_trend_per_district",
    "plot_stacked_bar_per_year",
    "plot_province_total_trend",
    "plot_percent_change",
    "generate_all_charts",
    "__version__",
]
