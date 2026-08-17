"""
mapping.py
===========
All cartographic / raster-to-PNG export functions used to produce the
article's figures:

  - convert_rasters_to_png()   : wraps lulc_toolkit.maps.generate_all_maps
                                  for the classified Dynamic World stack.
  - export_sentinel2_basemap() : GEE Sentinel-2 true-colour composite ->
                                  cartographic PNG (frame, graticule,
                                  scale bar, north arrow).
  - locator_map_syria()        : Jableh highlighted within Syria.
  - detail_map_with_inset()    : large Jableh detail panel + small Syria
                                  overview panel connected by zoom lines.

All functions in this module require Google Earth Engine credentials
and/or `cartopy` + real raster/vector data, and are intended to run in
the same Colab environment used throughout the project.
"""

from __future__ import annotations

import os
from pathlib import Path


def convert_rasters_to_png(input_dir: str, output_dir: str, class_dict=None) -> list[str]:
    """Thin wrapper around lulc_toolkit.maps.generate_all_maps -- converts
    every classified GeoTIFF in `input_dir` to a styled PNG map."""
    from lulc_toolkit.maps import generate_all_maps
    from lulc_toolkit.dynamic_world import DW_CLASSES

    os.makedirs(output_dir, exist_ok=True)
    class_dict = class_dict or DW_CLASSES
    png_files = generate_all_maps(in_dir=input_dir, out_dir=output_dir, class_dict=class_dict)
    print(f"Generated {len(png_files)} PNG maps in {output_dir}")
    return png_files


def export_sentinel2_basemap(
    geom,
    output_tif_local_path: str,
    drive_folder: str = "Jableh",
    export_name: str = "Jableh_HighRes_Basemap",
    date_range: tuple[str, str] = ("2026-01-01", "2026-07-01"),
    max_cloud_pct: float = 10,
    scale_m: float = 10,
    crs: str = "EPSG:32636",
):
    """
    Export a Sentinel-2 cloud-filtered median true-colour composite for
    `geom` to Google Drive, wait for completion, then convert to a
    cartographic PNG (frame, lon/lat graticule, scale bar, north arrow)
    via matplotlib + cartopy.

    Returns the path to the generated PNG.
    """
    import time
    import glob
    import numpy as np
    import rasterio
    import ee
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate(*date_range)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_pct))
        .median()
        .clip(geom)
    )
    vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.3}

    task = ee.batch.Export.image.toDrive(
        image=s2.visualize(**vis), description=export_name, folder=drive_folder,
        fileNamePrefix=export_name, region=geom, scale=scale_m, crs=crs, maxPixels=1e13,
    )
    task.start()
    while task.active():
        time.sleep(20)
    if task.status()["state"] != "COMPLETED":
        raise RuntimeError(f"GEE export failed: {task.status()}")

    candidates = glob.glob(os.path.join(f"/content/drive/MyDrive/{drive_folder}", f"{export_name}*.tif"))
    if not candidates:
        raise FileNotFoundError(f"Exported GeoTIFF not found in Drive/{drive_folder}")
    tif_path = candidates[0]

    with rasterio.open(tif_path) as src:
        rgb = src.read([1, 2, 3])
        rgb = np.transpose(rgb, (1, 2, 0)).astype(np.uint8)
        bounds = src.bounds
        epsg_code = src.crs.to_string().split(":")[1]

    data_crs = ccrs.epsg(epsg_code)
    fig = plt.figure(figsize=(10, 10), dpi=300)
    ax = plt.axes(projection=data_crs)
    ax.imshow(rgb, origin="upper",
              extent=[bounds.left, bounds.right, bounds.bottom, bounds.top], transform=data_crs)
    ax.set_extent([bounds.left, bounds.right, bounds.bottom, bounds.top], crs=data_crs)

    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=0.6,
                       color="white", alpha=0.6, linestyle="--")
    gl.top_labels = False
    gl.right_labels = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER

    for spine in ax.spines.values():
        spine.set_edgecolor("black")
        spine.set_linewidth(1.5)

    x0, x1, y0, y1 = ax.get_extent(crs=data_crs)
    sb_x, sb_y = x0 + (x1 - x0) * 0.08, y0 + (y1 - y0) * 0.05
    length_m = 2000
    ax.plot([sb_x, sb_x + length_m], [sb_y, sb_y], color="black", linewidth=3,
            transform=data_crs, solid_capstyle="butt")
    ax.text(sb_x + length_m / 2, sb_y + (y1 - y0) * 0.015, "2 km", transform=data_crs,
            ha="center", fontsize=9, fontweight="bold")

    ax.annotate("N", xy=(0.94, 0.90), xycoords="axes fraction", xytext=(0.94, 0.80),
                textcoords="axes fraction",
                arrowprops=dict(facecolor="black", width=4, headwidth=12),
                ha="center", va="center", fontsize=13, fontweight="bold")
    ax.set_title("Jableh District -- Sentinel-2 True-Colour Composite", fontsize=13,
                 fontweight="bold", pad=12)

    plt.tight_layout()
    plt.savefig(output_tif_local_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_tif_local_path


def locator_map_syria(jableh_geom, output_path: str):
    """Standalone "Jableh highlighted within Syria" overview map."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import cartopy.io.shapereader as shpreader
    from cartopy.io.shapereader import Reader

    syria_shp = shpreader.natural_earth(resolution="10m", category="cultural", name="admin_0_countries")
    syria_geom = None
    for rec in Reader(syria_shp).records():
        if rec.attributes.get("NAME") == "Syria" or rec.attributes.get("ADM0_A3") == "SYR":
            syria_geom = rec.geometry
            break
    if syria_geom is None:
        raise RuntimeError("Syria not found in Natural Earth admin_0_countries.")

    gov_shp = shpreader.natural_earth(resolution="10m", category="cultural", name="admin_1_states_provinces")
    governorates = [r for r in Reader(gov_shp).records() if r.attributes.get("admin") == "Syria"]

    fig = plt.figure(figsize=(9, 9), dpi=300)
    ax = plt.axes(projection=ccrs.PlateCarree())
    sx0, sy0, sx1, sy1 = syria_geom.bounds
    margin = 0.4
    ax.set_extent([sx0 - margin, sx1 + margin, sy0 - margin, sy1 + margin], crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.OCEAN, facecolor="#cfe8f0", zorder=0)
    ax.add_feature(cfeature.LAND, facecolor="#f5f0e6", zorder=0)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.6, zorder=2)
    ax.add_feature(cfeature.BORDERS, linewidth=0.8, linestyle=":", zorder=2)
    ax.add_geometries([syria_geom], crs=ccrs.PlateCarree(), facecolor="none",
                       edgecolor="black", linewidth=1.6, zorder=3)
    for rec in governorates:
        ax.add_geometries([rec.geometry], crs=ccrs.PlateCarree(), facecolor="none",
                           edgecolor="gray", linewidth=0.5, zorder=3)
    ax.add_geometries([jableh_geom], crs=ccrs.PlateCarree(), facecolor="#c4281b",
                       edgecolor="black", linewidth=1.2, alpha=0.85, zorder=4)

    gl = ax.gridlines(draw_labels=True, linewidth=0.4, color="gray", alpha=0.5, linestyle="--")
    gl.top_labels = False
    gl.right_labels = False

    red_patch = mpatches.Patch(facecolor="#c4281b", edgecolor="black", label="Jableh District")
    ax.legend(handles=[red_patch], loc="lower left", fontsize=9, framealpha=0.9)
    ax.set_title("Location of Jableh District within Syria", fontsize=13, fontweight="bold", pad=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path


def detail_map_with_inset(jableh_geom, output_path: str):
    """Large Jableh detail panel (right) + small Syria overview (left),
    connected by dashed zoom-indicator lines -- the figure used in the
    article's Study Area section."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import ConnectionPatch
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import cartopy.io.shapereader as shpreader
    from cartopy.io.shapereader import Reader

    jx0, jy0, jx1, jy1 = jableh_geom.bounds

    syria_shp = shpreader.natural_earth(resolution="10m", category="cultural", name="admin_0_countries")
    syria_geom = None
    for rec in Reader(syria_shp).records():
        if rec.attributes.get("NAME") == "Syria" or rec.attributes.get("ADM0_A3") == "SYR":
            syria_geom = rec.geometry
            break

    fig = plt.figure(figsize=(16, 9), dpi=300)

    ax_small = fig.add_axes([0.03, 0.15, 0.32, 0.7], projection=ccrs.PlateCarree())
    sx0, sy0, sx1, sy1 = syria_geom.bounds
    margin = 0.4
    ax_small.set_extent([sx0 - margin, sx1 + margin, sy0 - margin, sy1 + margin], crs=ccrs.PlateCarree())
    ax_small.add_feature(cfeature.OCEAN, facecolor="#cfe8f0", zorder=0)
    ax_small.add_feature(cfeature.LAND, facecolor="#f5f0e6", zorder=0)
    ax_small.add_feature(cfeature.COASTLINE, linewidth=0.6, zorder=2)
    ax_small.add_feature(cfeature.BORDERS, linewidth=0.8, linestyle=":", zorder=2)
    ax_small.add_geometries([syria_geom], crs=ccrs.PlateCarree(), facecolor="none",
                             edgecolor="black", linewidth=1.4, zorder=3)
    ax_small.add_geometries([jableh_geom], crs=ccrs.PlateCarree(), facecolor="#c4281b",
                             edgecolor="black", linewidth=0.8, zorder=5)
    ax_small.set_title("Syria", fontsize=11, fontweight="bold")

    box_pad = 0.35
    zx0, zy0, zx1, zy1 = jx0 - box_pad, jy0 - box_pad, jx1 + box_pad, jy1 + box_pad
    ax_small.add_patch(mpatches.Rectangle((zx0, zy0), zx1 - zx0, zy1 - zy0,
                        linewidth=1.4, edgecolor="red", facecolor="none", zorder=7,
                        transform=ccrs.PlateCarree()))

    ax_big = fig.add_axes([0.40, 0.08, 0.58, 0.85], projection=ccrs.PlateCarree())
    pad = 0.05
    ax_big.set_extent([jx0 - pad, jx1 + pad, jy0 - pad, jy1 + pad], crs=ccrs.PlateCarree())
    ax_big.add_feature(cfeature.OCEAN, facecolor="#cfe8f0", zorder=0)
    ax_big.add_feature(cfeature.LAND, facecolor="#f5f0e6", zorder=0)
    ax_big.add_feature(cfeature.COASTLINE, linewidth=0.8, zorder=2)
    ax_big.add_geometries([jableh_geom], crs=ccrs.PlateCarree(), facecolor="#c4281b",
                           edgecolor="black", linewidth=1.8, alpha=0.75, zorder=4)
    ax_big.set_title("Jableh District", fontsize=13, fontweight="bold")

    fig.canvas.draw()
    for (sx, sy), (bx, by) in [((zx1, zy1), (jx0 - pad, jy1 + pad)),
                                ((zx1, zy0), (jx0 - pad, jy0 - pad))]:
        con = ConnectionPatch(xyA=(sx, sy), coordsA=ax_small.transData,
                               xyB=(bx, by), coordsB=ax_big.transData,
                               axesA=ax_small, axesB=ax_big,
                               color="red", linewidth=1.0, linestyle="--", zorder=10)
        fig.add_artist(con)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return output_path
