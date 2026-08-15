"""Per-class pixel-count and area statistics for classified rasters."""

import glob
import os
import re

import numpy as np
import pandas as pd
import rasterio


def parse_tif_filename(fname: str, prefix: str = "DW_"):
    """
    Extract district name and year from a filename of the form
    ``'<prefix><district>_<year>.tif'``, e.g. ``'DW_Baqubah_2019.tif'``.

    Parameters
    ----------
    fname : str
        File path or file name.
    prefix : str
        Prefix used before the district name (e.g. ``'DW_'``).

    Returns
    -------
    tuple(str, int or None)
        ``(district_name, year)`` — year is ``None`` if the pattern
        doesn't match.
    """
    base = os.path.splitext(os.path.basename(fname))[0]
    pattern = rf"^{re.escape(prefix)}(.+)_(\d{{4}})$"
    m = re.match(pattern, base)
    if m:
        return m.group(1), int(m.group(2))
    return base, None


def compute_raster_stats(tif_path: str, class_names: dict, filename_prefix: str = "DW_"):
    """
    Compute per-class pixel counts and area (m², ha, km²) for one raster.

    Pixel area is computed in meters even for geographic (lon/lat) rasters,
    by approximating meters-per-degree at the raster's mean latitude. This
    is accurate enough for comparison/analysis purposes; for
    survey-grade area accuracy, reproject to a local UTM CRS first.

    Parameters
    ----------
    tif_path : str
        Path to a single-band classified GeoTIFF.
    class_names : dict
        ``{pixel_value: class_name}`` mapping.
    filename_prefix : str
        Prefix used to parse district/year from the filename.

    Returns
    -------
    list of dict
        One row per class present in the raster.
    """
    district, year = parse_tif_filename(tif_path, filename_prefix)

    with rasterio.open(tif_path) as src:
        data = src.read(1)
        nodata = src.nodata
        transform = src.transform
        crs = src.crs

        pixel_width = transform.a
        pixel_height = -transform.e

        if crs is not None and crs.is_geographic:
            bounds = src.bounds
            mean_lat = (bounds.top + bounds.bottom) / 2
            meters_per_deg_lon = 111320 * np.cos(np.radians(mean_lat))
            meters_per_deg_lat = 111320
            pixel_area_m2 = (pixel_width * meters_per_deg_lon) * (
                pixel_height * meters_per_deg_lat
            )
        else:
            pixel_area_m2 = pixel_width * pixel_height

    valid_mask = np.ones_like(data, dtype=bool)
    if nodata is not None:
        valid_mask &= data != nodata

    valid_data = data[valid_mask]
    total_valid_pixels = valid_data.size

    rows = []
    unique_vals, counts = np.unique(valid_data, return_counts=True)
    for val, cnt in zip(unique_vals, counts):
        class_name = class_names.get(int(val), f"unknown_{int(val)}")
        area_m2 = cnt * pixel_area_m2
        pct = (cnt / total_valid_pixels * 100) if total_valid_pixels > 0 else 0

        rows.append(
            {
                "district": district,
                "year": year,
                "class_value": int(val),
                "class_name": class_name,
                "pixel_count": int(cnt),
                "pixel_area_m2": round(pixel_area_m2, 4),
                "area_m2": round(area_m2, 2),
                "area_ha": round(area_m2 / 10000, 4),
                "area_km2": round(area_m2 / 1_000_000, 6),
                "percent_of_district": round(pct, 3),
                "total_valid_pixels": int(total_valid_pixels),
                "source_file": os.path.basename(tif_path),
            }
        )

    return rows


def build_statistics_table(
    in_dir: str,
    class_names: dict,
    out_csv_path: str,
    filename_prefix: str = "DW_",
) -> pd.DataFrame:
    """
    Compute per-class pixel/area statistics for every ``.tif`` file in
    ``in_dir`` and save the combined table as a CSV.

    Parameters
    ----------
    in_dir : str
        Folder containing input GeoTIFF files.
    class_names : dict
        ``{pixel_value: class_name}`` mapping.
    out_csv_path : str
        Path to save the resulting CSV table.
    filename_prefix : str
        Prefix used to parse district/year from each filename.

    Returns
    -------
    pandas.DataFrame
        The combined statistics table (district x year x class).
    """
    tif_files = sorted(glob.glob(os.path.join(in_dir, "*.tif")))
    if not tif_files:
        raise FileNotFoundError(f"No .tif files found in {in_dir}")

    print(f"Found {len(tif_files)} TIFF files")

    all_rows = []
    for i, tif_path in enumerate(tif_files, 1):
        print(f"[{i}/{len(tif_files)}] Processing: {os.path.basename(tif_path)} ...")
        try:
            rows = compute_raster_stats(tif_path, class_names, filename_prefix)
            all_rows.extend(rows)
            print(f"  ✓ Extracted {len(rows)} classes")
        except Exception as e:
            print(f"  ✗ Error processing {tif_path}: {e}")

    df = (
        pd.DataFrame(all_rows)
        .sort_values(["district", "year", "class_value"])
        .reset_index(drop=True)
    )

    out_dir = os.path.dirname(out_csv_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    df.to_csv(out_csv_path, index=False, encoding="utf-8-sig")
    print(f"\n✓ Statistics table saved to: {out_csv_path} ({len(df)} rows)")

    return df


def build_pivot_table(df: pd.DataFrame, out_csv_path: str, value_col: str = "area_km2") -> pd.DataFrame:
    """
    Build a wide pivot table (district, year as rows; class_name as
    columns) from the detailed statistics DataFrame, and save it as CSV.

    Parameters
    ----------
    df : pandas.DataFrame
        Output of :func:`build_statistics_table`.
    out_csv_path : str
        Path to save the pivoted CSV.
    value_col : str
        Which numeric column to pivot on (default: ``'area_km2'``).

    Returns
    -------
    pandas.DataFrame
    """
    pivot = df.pivot_table(
        index=["district", "year"],
        columns="class_name",
        values=value_col,
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    out_dir = os.path.dirname(out_csv_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pivot.to_csv(out_csv_path, index=False, encoding="utf-8-sig")
    print(f"✓ Pivot table saved to: {out_csv_path}")
    return pivot
