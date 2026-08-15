"""
End-to-end example: download Dynamic World data for every district in a
shapefile, for a set of years, then generate maps, statistics, and charts.

Intended to run in Google Colab. Edit the CONFIG block below, then run
this script (or paste its contents into a Colab cell / import and call
`main()`).
"""

import os

from lulc_toolkit import (
    authenticate_ee,
    mount_drive_readonly,
    find_archive_in_drive,
    extract_shapefile_archive,
    load_shapefile,
    download_dynamicworld_for_years,
    DW_CLASSES,
    DW_CLASS_NAMES,
    generate_all_maps,
    build_statistics_table,
    build_pivot_table,
    generate_all_charts,
    zip_and_download,
)

# ============================== CONFIG ======================================
PROJECT_ID = "dyalaali"          # your Earth Engine project id
SEARCH_KEYWORD = "diyala"        # substring matching your shapefile archive's filename in Drive
NAME_FIELD = "ADM3_EN"           # column in the shapefile holding each district's name
YEARS = [2014, 2019, 2024]       # years to download (pre-2015 years are skipped automatically)

SHAPEFILE_EXTRACT_DIR = "/content/shapefile_data"
DW_OUT_DIR = "/content/DynamicWorld_Output"
MAPS_OUT_DIR = "/content/DynamicWorld_Maps_PNG"
STATS_OUT_DIR = "/content/DynamicWorld_Stats"
CHARTS_OUT_DIR = "/content/DynamicWorld_Charts"
# ==============================================================================


def main():
    # 1. Authenticate Earth Engine
    authenticate_ee(PROJECT_ID)

    # 2. Locate and load the shapefile (Drive is read-only here)
    mount_drive_readonly()
    archive_path = find_archive_in_drive(SEARCH_KEYWORD)
    if archive_path is None:
        raise FileNotFoundError(
            f"No archive containing '{SEARCH_KEYWORD}' found in Drive. "
            f"Change SEARCH_KEYWORD to match your file name."
        )
    print("✓ Archive found:", archive_path)

    shp_path = extract_shapefile_archive(archive_path, SHAPEFILE_EXTRACT_DIR)
    gdf = load_shapefile(shp_path)

    name_field = NAME_FIELD if NAME_FIELD in gdf.columns else gdf.columns[0]
    print(f"  Naming files using field: {name_field}")

    # 3. Download Dynamic World composites
    downloaded_files, skipped = download_dynamicworld_for_years(
        gdf=gdf,
        name_field=name_field,
        years=YEARS,
        out_dir=DW_OUT_DIR,
    )

    # 4. Generate PNG maps
    generated_maps = generate_all_maps(
        in_dir=DW_OUT_DIR,
        out_dir=MAPS_OUT_DIR,
        class_dict=DW_CLASSES,
        source_label="GOOGLE/DYNAMICWORLD/V1",
    )

    # 5. Build statistics table + pivot table
    stats_csv = os.path.join(STATS_OUT_DIR, "DynamicWorld_Statistics.csv")
    stats_df = build_statistics_table(
        in_dir=DW_OUT_DIR,
        class_names=DW_CLASS_NAMES,
        out_csv_path=stats_csv,
    )

    pivot_csv = os.path.join(STATS_OUT_DIR, "DynamicWorld_Statistics_Pivot_km2.csv")
    build_pivot_table(stats_df, out_csv_path=pivot_csv, value_col="area_km2")

    # 6. Generate charts
    generated_charts = generate_all_charts(stats_df, out_dir=CHARTS_OUT_DIR)

    # 7. Zip and download everything
    zip_and_download(
        [stats_csv, pivot_csv] + generated_maps + generated_charts,
        zip_path="/content/DynamicWorld_All_Outputs.zip",
    )


if __name__ == "__main__":
    main()
